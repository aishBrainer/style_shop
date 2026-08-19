"""Idempotent bootstrap data.

Runs on every API start (see docker-compose). Safe to re-run: everything here
is an upsert keyed on a natural identifier.

Seeds:
  * feature flags (§69)
  * the AI model registry, with licence status (§50, §72)
  * background prompt templates (§68)
  * a development admin account, in non-production environments only
"""

from __future__ import annotations

import os

from sqlalchemy import select

from app.ai.pipelines.image_ops import BACKGROUND_PRESETS
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import SyncSessionLocal
from app.models import AIModel, FeatureFlag, PromptTemplate, User
from app.models.enums import AIModelType, CommercialUse, UserRole
from app.services.feature_flags import DEFAULT_FLAGS

configure_logging(settings.log_level, json_output=False)
log = get_logger(__name__)


#: §50 registry seed. `enabled` is driven by licence status, not convenience —
#: anything not cleared for commercial use ships disabled (§72).
AI_MODELS: list[dict] = [
    {
        "key": "mock",
        "name": "Mock Virtual Try-On (CPU reference)",
        "type": AIModelType.VTON,
        "provider_class": "app.ai.providers.mock:MockVirtualTryOn",
        "framework": "pillow",
        "vram_requirement_mb": 0,
        "license": "MIT",
        "commercial_use": CommercialUse.ALLOWED,
        "enabled": True,
        "priority": 100,
        "license_notes": "Development placeholder. Produces a composite, not a real try-on.",
    },
    {
        "key": "catvton",
        "name": "CatVTON",
        "type": AIModelType.VTON,
        "provider_class": "app.ai.providers.catvton:CatVTONEngine",
        "framework": "pytorch",
        "vram_requirement_mb": 8192,
        "license": "CC BY-NC-SA 4.0",
        "license_url": "https://github.com/Zheng-Chong/CatVTON",
        "commercial_use": CommercialUse.NOT_ALLOWED,
        "enabled": False,
        "priority": 10,
        "license_notes": (
            "Non-commercial licence — not deployable in a paid SaaS. "
            "Benchmarking only. See MODEL_LICENSE.md."
        ),
    },
    {
        "key": "rembg",
        "name": "rembg / U²-Net",
        "type": AIModelType.SEGMENTATION,
        "provider_class": "app.ai.providers.rembg_provider:RembgSegmentation",
        "framework": "onnxruntime",
        "vram_requirement_mb": 0,
        "license": "MIT + Apache-2.0",
        "license_url": "https://github.com/danielgatis/rembg",
        "commercial_use": CommercialUse.ALLOWED,
        "enabled": True,
        "priority": 100,
    },
    {
        "key": "sam2",
        "name": "Segment Anything 2",
        "type": AIModelType.SEGMENTATION,
        "provider_class": "app.ai.providers.sam2:SAM2Segmentation",
        "framework": "pytorch",
        "vram_requirement_mb": 4096,
        "license": "Apache-2.0",
        "license_url": "https://github.com/facebookresearch/sam2",
        "commercial_use": CommercialUse.ALLOWED,
        "enabled": False,
        "priority": 90,
        "license_notes": "Requires the GPU image and a downloaded checkpoint.",
    },
    {
        "key": "mock",
        "name": "Mock Image Generation (CPU reference)",
        "type": AIModelType.IMAGE_GENERATION,
        "provider_class": "app.ai.providers.mock:MockImageGeneration",
        "framework": "pillow",
        "vram_requirement_mb": 0,
        "license": "MIT",
        "commercial_use": CommercialUse.ALLOWED,
        "enabled": True,
        "priority": 100,
    },
    {
        "key": "sdxl",
        "name": "SDXL (diffusers)",
        "type": AIModelType.IMAGE_GENERATION,
        "provider_class": "app.ai.providers.diffusers_provider:DiffusersImageGeneration",
        "framework": "pytorch",
        "vram_requirement_mb": 10240,
        "license": "CreativeML Open RAIL++-M",
        "license_url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
        "commercial_use": CommercialUse.UNREVIEWED,
        "enabled": False,
        "priority": 50,
        "license_notes": (
            "Open RAIL++-M permits commercial use but attaches use restrictions "
            "you must pass on to your users. Review before enabling."
        ),
    },
    {
        "key": "mock",
        "name": "Lanczos Upscale (CPU reference)",
        "type": AIModelType.UPSCALE,
        "provider_class": "app.ai.providers.mock:MockUpscale",
        "framework": "pillow",
        "vram_requirement_mb": 0,
        "license": "MIT",
        "commercial_use": CommercialUse.ALLOWED,
        "enabled": True,
        "priority": 100,
    },
    {
        "key": "realesrgan",
        "name": "Real-ESRGAN x4plus",
        "type": AIModelType.UPSCALE,
        "provider_class": "app.ai.providers.realesrgan:RealESRGANUpscale",
        "framework": "pytorch",
        "vram_requirement_mb": 2048,
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/xinntao/Real-ESRGAN",
        "commercial_use": CommercialUse.ALLOWED,
        "enabled": False,
        "priority": 90,
        "license_notes": "Requires the GPU image and downloaded weights.",
    },
]


def seed_feature_flags(session) -> int:
    created = 0
    for key, (description, enabled) in DEFAULT_FLAGS.items():
        existing = session.scalar(select(FeatureFlag).where(FeatureFlag.key == key))
        if existing is None:
            session.add(
                FeatureFlag(key=key, description=description, enabled=enabled, rollout_percentage=100)
            )
            created += 1
    return created


def seed_ai_models(session) -> int:
    created = 0
    for spec in AI_MODELS:
        existing = session.scalar(
            select(AIModel).where(AIModel.key == spec["key"], AIModel.type == spec["type"])
        )
        if existing is not None:
            # Licence facts are ours to correct on redeploy; `enabled` is the
            # operator's decision and must not be stomped.
            existing.license = spec["license"]
            existing.license_url = spec.get("license_url")
            existing.commercial_use = spec["commercial_use"]
            existing.license_notes = spec.get("license_notes")
            existing.provider_class = spec["provider_class"]
            continue

        session.add(AIModel(version="1", **spec))
        created += 1
    return created


def seed_prompt_templates(session) -> int:
    created = 0
    for order, (key, prompt) in enumerate(BACKGROUND_PRESETS.items()):
        existing = session.scalar(select(PromptTemplate).where(PromptTemplate.key == key))
        if existing is not None:
            continue
        session.add(
            PromptTemplate(
                key=key,
                label=key.replace("_", " ").title(),
                category="background",
                prompt=prompt,
                negative_prompt="blurry, low quality, distorted, watermark, text",
                sort_order=order,
            )
        )
        created += 1
    return created


def seed_dev_admin(session) -> bool:
    """Create an administrator for local development.

    Never in production: an account with a known password in a live deployment
    is a backdoor, not a convenience. Set ADMIN_EMAIL/ADMIN_PASSWORD to
    provision a real admin there instead.
    """
    if settings.is_production:
        return False

    email = os.getenv("ADMIN_EMAIL", "admin@aifashionstudio.local").lower()
    password = os.getenv("ADMIN_PASSWORD", "changeme-admin-123")

    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        if existing.role != UserRole.ADMIN:
            existing.role = UserRole.ADMIN
        return False

    from app.core.security import hash_password
    from app.db.base import utcnow
    from app.models import Membership, Organization
    from app.models.enums import MembershipRole, PlanTier
    from app.services.credits import PLAN_LIMITS, SIGNUP_GRANT

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name="Studio Admin",
        role=UserRole.ADMIN,
        email_verified_at=utcnow(),
    )
    session.add(user)
    session.flush()

    org = Organization(
        name="Admin Studio",
        slug="admin-studio",
        is_personal=True,
        plan=PlanTier.BUSINESS,
        credit_balance=SIGNUP_GRANT * 40,
        **PLAN_LIMITS[PlanTier.BUSINESS],
    )
    session.add(org)
    session.flush()

    session.add(
        Membership(
            user_id=user.id,
            organization_id=org.id,
            role=MembershipRole.OWNER,
            accepted_at=utcnow(),
        )
    )
    user.default_organization_id = org.id
    session.flush()

    log.info("seed.dev_admin_created", email=email)
    return True


def main() -> None:
    with SyncSessionLocal() as session:
        flags = seed_feature_flags(session)
        models = seed_ai_models(session)
        prompts = seed_prompt_templates(session)
        admin = seed_dev_admin(session)
        session.commit()

    log.info(
        "seed.complete",
        feature_flags=flags,
        ai_models=models,
        prompt_templates=prompts,
        dev_admin=admin,
    )


if __name__ == "__main__":
    main()
