"""Projects, products, model library and brand kits (§34, §10, §11, §12, §32)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.core.deps import CurrentPrincipal, DbSession, WritePrincipal
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db.base import utcnow
from app.models import Asset, BrandKit, GenerationJob, ModelProfile, Product, Project
from app.models.enums import (
    AssetType,
    ClothingStyle,
    ModelAgeGroup,
    ModelBodyType,
    ModelGender,
    ModelPose,
)
from app.schemas.catalog import (
    AssetOut,
    BrandKitOut,
    BrandKitUpsert,
    ModelProfileCreate,
    ModelProfileOut,
    ModelProfileUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from app.schemas.common import Message, Page
from app.services import assets as asset_service
from app.storage.s3 import get_storage

router = APIRouter(tags=["catalog"])


# ---------------------------------------------------------------- projects --

@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate, session: DbSession, principal: WritePrincipal
) -> ProjectOut:
    existing = int(
        await session.scalar(
            select(func.count(Project.id)).where(
                Project.organization_id == principal.organization_id,
                Project.deleted_at.is_(None),
            )
        )
        or 0
    )
    if existing >= principal.organization.max_projects:
        raise ForbiddenError(
            f"Your plan allows {principal.organization.max_projects} projects. "
            f"Archive one or upgrade to add more.",
            code="PROJECT_LIMIT_REACHED",
        )

    project = Project(
        organization_id=principal.organization_id,
        created_by_id=principal.user_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(project)
    await session.flush()
    return ProjectOut.model_validate(project)


@router.get("/projects", response_model=Page[ProjectOut])
async def list_projects(
    session: DbSession,
    principal: CurrentPrincipal,
    include_archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> Page[ProjectOut]:
    conditions = [
        Project.organization_id == principal.organization_id,
        Project.deleted_at.is_(None),
    ]
    if not include_archived:
        conditions.append(Project.is_archived.is_(False))

    total = int(await session.scalar(select(func.count(Project.id)).where(*conditions)) or 0)
    rows = (
        await session.scalars(
            select(Project)
            .where(*conditions)
            .order_by(Project.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[ProjectOut] = []
    for project in rows:
        out = ProjectOut.model_validate(project)
        out.asset_count = await asset_service.count_for_project(session, project.id)
        out.generation_count = int(
            await session.scalar(
                select(func.count(GenerationJob.id)).where(
                    GenerationJob.project_id == project.id
                )
            )
            or 0
        )
        if project.cover_asset_id:
            cover = await session.get(Asset, project.cover_asset_id)
            if cover is not None:
                out.cover_url = get_storage().signed_url(
                    cover.thumbnail_key or cover.storage_key
                )
        items.append(out)

    return Page[ProjectOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> ProjectOut:
    project = await _owned_project(session, project_id, principal.organization_id)
    out = ProjectOut.model_validate(project)
    out.asset_count = await asset_service.count_for_project(session, project.id)
    return out


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: DbSession,
    principal: WritePrincipal,
) -> ProjectOut:
    project = await _owned_project(session, project_id, principal.organization_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.flush()
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", response_model=Message)
async def delete_project(
    project_id: uuid.UUID, session: DbSession, principal: WritePrincipal
) -> Message:
    project = await _owned_project(session, project_id, principal.organization_id)
    project.deleted_at = utcnow()
    await session.flush()
    return Message(message="Project deleted.")


async def _owned_project(session, project_id: uuid.UUID, organization_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found.")
    if project.organization_id != organization_id:
        raise NotFoundError("Project not found.")
    return project


# ---------------------------------------------------------------- products --

@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    payload: ProductCreate, session: DbSession, principal: WritePrincipal
) -> ProductOut:
    image = await asset_service.get_owned(
        session, payload.image_asset_id, principal.organization_id
    )

    product = Product(
        organization_id=principal.organization_id,
        project_id=payload.project_id,
        created_by_id=principal.user_id,
        name=payload.name,
        sku=payload.sku,
        description=payload.description,
        image_asset_id=image.id,
        category=payload.category,
    )
    session.add(product)
    await session.flush()

    # §10 step 2: analysis runs on the CPU queue so upload returns immediately.
    # Committing first guarantees the worker can see the row.
    await session.commit()

    from app.queue.tasks import analyse_product

    analyse_product.apply_async(args=[str(product.id)], queue="cpu")

    out = ProductOut.model_validate(product)
    out.image = asset_service.to_out(image)
    return out


@router.get("/products", response_model=Page[ProductOut])
async def list_products(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: uuid.UUID | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> Page[ProductOut]:
    conditions = [
        Product.organization_id == principal.organization_id,
        Product.deleted_at.is_(None),
    ]
    if project_id is not None:
        conditions.append(Product.project_id == project_id)
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern)))

    total = int(await session.scalar(select(func.count(Product.id)).where(*conditions)) or 0)
    rows = (
        await session.scalars(
            select(Product)
            .where(*conditions)
            .order_by(Product.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[ProductOut] = []
    for product in rows:
        out = ProductOut.model_validate(product)
        image = await session.get(Asset, product.image_asset_id)
        if image is not None:
            out.image = asset_service.to_out(image)
        items.append(out)

    return Page[ProductOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID, session: DbSession, principal: CurrentPrincipal
) -> ProductOut:
    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise NotFoundError("Product not found.")
    if product.organization_id != principal.organization_id:
        raise NotFoundError("Product not found.")

    out = ProductOut.model_validate(product)
    image = await session.get(Asset, product.image_asset_id)
    if image is not None:
        out.image = asset_service.to_out(image)
    return out


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    session: DbSession,
    principal: WritePrincipal,
) -> ProductOut:
    product = await session.get(Product, product_id)
    if product is None or product.organization_id != principal.organization_id:
        raise NotFoundError("Product not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await session.flush()
    return ProductOut.model_validate(product)


@router.delete("/products/{product_id}", response_model=Message)
async def delete_product(
    product_id: uuid.UUID, session: DbSession, principal: WritePrincipal
) -> Message:
    product = await session.get(Product, product_id)
    if product is None or product.organization_id != principal.organization_id:
        raise NotFoundError("Product not found.")
    product.deleted_at = utcnow()
    await session.flush()
    return Message(message="Product deleted.")


# ----------------------------------------------------------- model library --

@router.get("/models", response_model=Page[ModelProfileOut])
async def list_models(
    session: DbSession,
    principal: CurrentPrincipal,
    gender: ModelGender | None = None,
    age_group: ModelAgeGroup | None = None,
    body_type: ModelBodyType | None = None,
    pose: ModelPose | None = None,
    style: ClothingStyle | None = None,
    collection: str | None = None,
    custom_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> Page[ModelProfileOut]:
    """§11 — platform library plus this workspace's own uploads."""
    conditions = [ModelProfile.deleted_at.is_(None), ModelProfile.is_active.is_(True)]

    if custom_only:
        conditions.append(ModelProfile.organization_id == principal.organization_id)
    else:
        conditions.append(
            or_(
                ModelProfile.organization_id.is_(None),  # platform library
                ModelProfile.organization_id == principal.organization_id,
            )
        )

    for column, value in (
        (ModelProfile.gender, gender),
        (ModelProfile.age_group, age_group),
        (ModelProfile.body_type, body_type),
        (ModelProfile.pose, pose),
        (ModelProfile.style, style),
        (ModelProfile.collection, collection),
    ):
        if value is not None:
            conditions.append(column == value)

    total = int(
        await session.scalar(select(func.count(ModelProfile.id)).where(*conditions)) or 0
    )
    rows = (
        await session.scalars(
            select(ModelProfile)
            .where(*conditions)
            .order_by(ModelProfile.sort_order, ModelProfile.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[ModelProfileOut] = []
    for profile in rows:
        out = ModelProfileOut.model_validate(profile)
        image = await session.get(Asset, profile.image_asset_id)
        if image is not None:
            out.image = asset_service.to_out(image)
        items.append(out)

    return Page[ModelProfileOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/models", response_model=ModelProfileOut, status_code=201)
async def create_model(
    payload: ModelProfileCreate, session: DbSession, principal: WritePrincipal
) -> ModelProfileOut:
    """§12 custom model upload. Validation runs async; the profile is inactive
    until it passes, so an unusable photo cannot reach a generation."""
    image = await asset_service.get_owned(
        session, payload.image_asset_id, principal.organization_id
    )

    profile = ModelProfile(
        organization_id=principal.organization_id,
        created_by_id=principal.user_id,
        name=payload.name,
        image_asset_id=image.id,
        gender=payload.gender,
        age_group=payload.age_group,
        body_type=payload.body_type,
        pose=payload.pose,
        style=payload.style,
        is_builtin=False,
        is_active=False,
    )
    session.add(profile)
    await session.flush()
    await session.commit()

    from app.queue.tasks import validate_model_profile

    validate_model_profile.apply_async(args=[str(profile.id)], queue="cpu")

    out = ModelProfileOut.model_validate(profile)
    out.image = asset_service.to_out(image)
    return out


@router.patch("/models/{model_id}", response_model=ModelProfileOut)
async def update_model(
    model_id: uuid.UUID,
    payload: ModelProfileUpdate,
    session: DbSession,
    principal: WritePrincipal,
) -> ModelProfileOut:
    profile = await session.get(ModelProfile, model_id)
    # Platform library models are read-only for customers.
    if profile is None or profile.organization_id != principal.organization_id:
        raise NotFoundError("Model not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await session.flush()
    return ModelProfileOut.model_validate(profile)


@router.delete("/models/{model_id}", response_model=Message)
async def delete_model(
    model_id: uuid.UUID, session: DbSession, principal: WritePrincipal
) -> Message:
    profile = await session.get(ModelProfile, model_id)
    if profile is None or profile.organization_id != principal.organization_id:
        raise NotFoundError("Model not found.")
    profile.deleted_at = utcnow()
    await session.flush()
    return Message(message="Model deleted.")


# ------------------------------------------------------------- brand kits ---

@router.get("/brand-kit", response_model=BrandKitOut | None)
async def get_brand_kit(session: DbSession, principal: CurrentPrincipal) -> BrandKitOut | None:
    kit = await session.scalar(
        select(BrandKit)
        .where(
            BrandKit.organization_id == principal.organization_id,
            BrandKit.deleted_at.is_(None),
        )
        .order_by(BrandKit.is_default.desc(), BrandKit.created_at)
    )
    if kit is None:
        return None

    out = BrandKitOut.model_validate(kit)
    if kit.logo_asset_id:
        logo = await session.get(Asset, kit.logo_asset_id)
        if logo is not None:
            out.logo_url = get_storage().signed_url(logo.storage_key)
    return out


@router.put("/brand-kit", response_model=BrandKitOut)
async def upsert_brand_kit(
    payload: BrandKitUpsert, session: DbSession, principal: WritePrincipal
) -> BrandKitOut:
    kit = await session.scalar(
        select(BrandKit).where(
            BrandKit.organization_id == principal.organization_id,
            BrandKit.deleted_at.is_(None),
        )
    )
    if kit is None:
        kit = BrandKit(organization_id=principal.organization_id, is_default=True)
        session.add(kit)

    if payload.logo_asset_id is not None:
        await asset_service.get_owned(
            session, payload.logo_asset_id, principal.organization_id
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(kit, field, value)

    await session.flush()
    return BrandKitOut.model_validate(kit)
