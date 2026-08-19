"""Celery tasks — one per job type.

Each task is deliberately thin (§92): open a JobContext, call a pipeline, save
what comes back. All AI logic lives in app.ai.pipelines; all bookkeeping lives
in app.workers.runtime.
"""

from __future__ import annotations

import uuid
from typing import Any

from celery import Task

from app.ai.pipelines import analysis, image_ops, vton
from app.ai.registry import configured_provider
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import worker_session
from app.models import Asset, ModelProfile, Product
from app.models.enums import AIModelType, AssetType, GarmentCategory, JobStatus, PlanTier
from app.queue.celery_app import celery
from app.workers.runtime import run_job

log = get_logger(__name__)

# Default retry policy for transient failures (§64).
RETRY_KWARGS = {
    "autoretry_for": (Exception,),
    "retry_backoff": 10,
    "retry_backoff_max": 120,
    "retry_jitter": True,
    "max_retries": 2,
}


class JobTask(Task):
    """Records the retry count on the job row so the UI and admin can see it."""

    def on_retry(self, exc, task_id, args, kwargs, einfo):  # noqa: D102
        job_id = kwargs.get("job_id") or (args[0] if args else None)
        if not job_id:
            return
        try:
            with worker_session() as session:
                from app.models import GenerationJob

                job = session.get(GenerationJob, uuid.UUID(str(job_id)))
                if job is not None:
                    job.retry_count += 1
                    job.status = JobStatus.QUEUED
                    job.progress = 0
        except Exception as inner:  # noqa: BLE001
            log.warning("task.retry_bookkeeping_failed", error=str(inner))


def _watermark_for(ctx) -> bool:
    """§4.2 — free-tier output carries a watermark."""
    from app.models import Organization

    org = ctx.session.get(Organization, ctx.job.organization_id)
    return org is not None and org.plan == PlanTier.FREE


# ------------------------------------------------------------------- VTON ---

@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_vton_job", queue="vton", **RETRY_KWARGS)
def run_vton_job(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.set_status(JobStatus.PREPROCESSING)
        person = ctx.require_image(params.get("person_asset_id"), "model")
        garment = ctx.require_image(params.get("garment_asset_id"), "garment")
        mask = ctx.load_image(ctx.job.mask_asset_id)

        ctx.job.ai_model_key = configured_provider(AIModelType.VTON)
        ctx.set_status(JobStatus.PROCESSING)

        result = vton.run_vton(
            vton.VTONRequest(
                person=person,
                garment=garment,
                mask=mask,
                category=GarmentCategory(params.get("category", GarmentCategory.UPPER_BODY)),
                seed=ctx.job.seed,
                steps=int(params.get("steps", 30)),
                guidance_scale=float(params.get("guidance_scale", 2.0)),
                hd=bool(params.get("hd", False)),
                num_images=int(params.get("num_images", 1)),
                auto_mask=bool(params.get("auto_mask", True)),
                preserve_face=bool(params.get("preserve_face", True)),
            ),
            on_progress=ctx.progress,
        )

        _finish(ctx, result, watermark=_watermark_for(ctx))
    return job_id


# ------------------------------------------------------------ image studio --

@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_background_remove", queue="cpu", **RETRY_KWARGS)
def run_background_remove(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "source")

        result = image_ops.remove_background(
            image,
            background=params.get("background", "transparent"),
            background_color=params.get("background_color", "#FFFFFF"),
            on_progress=ctx.progress,
        )
        # Transparency only survives PNG.
        mime = "image/png" if params.get("background", "transparent") == "transparent" else "image/jpeg"
        _finish(ctx, result, mime_type=mime, watermark=_watermark_for(ctx))
    return job_id


@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_background_replace", queue="image", **RETRY_KWARGS)
def run_background_replace(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.job.ai_model_key = configured_provider(AIModelType.IMAGE_GENERATION)
        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "source")

        result = image_ops.replace_background(
            image,
            preset=params.get("preset"),
            prompt=params.get("prompt"),
            seed=ctx.job.seed,
            steps=int(params.get("steps", 30)),
            on_progress=ctx.progress,
        )
        _finish(ctx, result, watermark=_watermark_for(ctx))
    return job_id


@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_product_photography", queue="image", **RETRY_KWARGS)
def run_product_photography(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.job.ai_model_key = configured_provider(AIModelType.IMAGE_GENERATION)
        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "product")

        result = image_ops.product_photography(
            image,
            background=params.get("background", "studio"),
            lighting=params.get("lighting", "studio"),
            camera=params.get("camera", "medium"),
            composition=params.get("composition", "center"),
            custom_prompt=params.get("prompt"),
            seed=ctx.job.seed,
            steps=int(params.get("steps", 30)),
            on_progress=ctx.progress,
        )
        _finish(ctx, result, watermark=_watermark_for(ctx))
    return job_id


@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_inpaint", queue="image", **RETRY_KWARGS)
def run_inpaint(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.job.ai_model_key = configured_provider(AIModelType.IMAGE_GENERATION)
        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "source")
        mask = ctx.require_image(ctx.job.mask_asset_id or params.get("mask_asset_id"), "mask")

        if ctx.job.type == "object_remove":
            result = image_ops.remove_object(
                image, mask, seed=ctx.job.seed,
                steps=int(params.get("steps", 30)), on_progress=ctx.progress,
            )
        else:
            result = image_ops.inpaint(
                image, mask,
                prompt=params.get("prompt", ""),
                seed=ctx.job.seed,
                steps=int(params.get("steps", 30)),
                strength=float(params.get("strength", 0.9)),
                on_progress=ctx.progress,
            )
        _finish(ctx, result, watermark=_watermark_for(ctx))
    return job_id


@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_expand", queue="image", **RETRY_KWARGS)
def run_expand(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.job.ai_model_key = configured_provider(AIModelType.IMAGE_GENERATION)
        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "source")

        result = image_ops.expand_canvas(
            image,
            left=int(params.get("left", 0)),
            right=int(params.get("right", 0)),
            top=int(params.get("top", 0)),
            bottom=int(params.get("bottom", 0)),
            prompt=params.get("prompt"),
            seed=ctx.job.seed,
            steps=int(params.get("steps", 30)),
            on_progress=ctx.progress,
        )
        _finish(ctx, result, watermark=_watermark_for(ctx))
    return job_id


@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_upscale", queue="image", **RETRY_KWARGS)
def run_upscale(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.job.ai_model_key = configured_provider(AIModelType.UPSCALE)
        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "source")

        result = image_ops.upscale(
            image, scale=int(params.get("scale", 2)), on_progress=ctx.progress
        )
        _finish(ctx, result, watermark=_watermark_for(ctx))
    return job_id


@celery.task(base=JobTask, bind=True, name="app.queue.tasks.run_enhance", queue="cpu", **RETRY_KWARGS)
def run_enhance(self, job_id: str) -> str:
    with run_job(job_id, self.request.hostname) as ctx:
        if ctx is None:
            return job_id
        params = ctx.job.params or {}

        ctx.set_status(JobStatus.PROCESSING)
        image = ctx.require_image(params.get("image_asset_id"), "source")

        result = image_ops.enhance(
            image,
            brightness=float(params.get("brightness", 1.0)),
            contrast=float(params.get("contrast", 1.0)),
            saturation=float(params.get("saturation", 1.0)),
            sharpness=float(params.get("sharpness", 1.0)),
            blur=float(params.get("blur", 0.0)),
            auto=bool(params.get("auto", False)),
            on_progress=ctx.progress,
        )
        _finish(ctx, result, mime_type="image/jpeg", watermark=_watermark_for(ctx))
    return job_id


# --------------------------------------------------- analysis (§10, §12) ----

@celery.task(bind=True, name="app.queue.tasks.analyse_product", queue="cpu", max_retries=1)
def analyse_product(self, product_id: str) -> dict[str, Any]:
    """Runs right after a product upload so the studio can pre-select the
    garment category. Never fails the upload — worst case the user picks."""
    from app.services import imaging
    from app.storage.keys import asset_key
    from app.storage.s3 import get_storage

    storage = get_storage()
    with worker_session() as session:
        product = session.get(Product, uuid.UUID(product_id))
        if product is None:
            return {"error": "not_found"}

        source = session.get(Asset, product.image_asset_id)
        if source is None:
            return {"error": "asset_missing"}

        image = imaging.load(storage.get(source.storage_key))
        result = analysis.analyse_product(image)

        product.category = result.category
        product.category_confidence = result.confidence
        product.bounding_box = result.bounding_box
        product.analysis = result.details

        # Persist the mask so try-on does not recompute it per generation.
        if result.mask is not None:
            mask_id = uuid.uuid4()
            data = imaging.encode(result.mask.convert("L"), "image/png")
            key = asset_key(product.organization_id, AssetType.MASK, mask_id, "original", "image/png")
            storage.put(key, data, "image/png")

            mask_asset = Asset(
                id=mask_id,
                organization_id=product.organization_id,
                project_id=product.project_id,
                owner_id=product.created_by_id,
                type=AssetType.MASK,
                filename=f"mask-{mask_id.hex[:8]}.png",
                mime_type="image/png",
                size_bytes=len(data),
                width=result.mask.width,
                height=result.mask.height,
                storage_key=key,
            )
            session.add(mask_asset)
            session.flush()
            product.mask_asset_id = mask_asset.id

        return {
            "product_id": product_id,
            "category": str(result.category),
            "confidence": result.confidence,
        }


@celery.task(bind=True, name="app.queue.tasks.validate_model_profile", queue="cpu", max_retries=1)
def validate_model_profile(self, model_profile_id: str) -> dict[str, Any]:
    """§12 — flags an unusable custom model photo before a credit is spent."""
    from app.services import imaging
    from app.storage.s3 import get_storage

    storage = get_storage()
    with worker_session() as session:
        profile = session.get(ModelProfile, uuid.UUID(model_profile_id))
        if profile is None:
            return {"error": "not_found"}

        source = session.get(Asset, profile.image_asset_id)
        if source is None:
            return {"error": "asset_missing"}

        image = imaging.load(storage.get(source.storage_key))
        result = analysis.validate_model_image(image)

        profile.validation = {
            "acceptable": result.acceptable,
            "reasons": result.reasons,
            "message": None if result.acceptable else analysis.ModelValidation.REJECTION_MESSAGE,
            **result.details,
        }
        profile.validated_at = utcnow()
        # Unusable photos stay in the library but are hidden from the picker.
        profile.is_active = result.acceptable

        return {"model_profile_id": model_profile_id, "acceptable": result.acceptable}


# ------------------------------------------------------------------ shared --

def _finish(ctx, result, *, mime_type: str = "image/png", watermark: bool = False) -> None:
    ctx.set_status(JobStatus.POST_PROCESSING)

    # Record the parameters the engine actually used (§66) — including any
    # seed it chose for us, so the generation can be reproduced (§67).
    ctx.job.params = {**(ctx.job.params or {}), **result.params}
    if ctx.job.seed is None and result.params.get("seed") is not None:
        ctx.job.seed = int(result.params["seed"])

    ctx.set_status(JobStatus.UPLOADING)
    assets = [
        ctx.save_image(img, mime_type=mime_type, params=result.params, watermark=watermark)
        for img in result.images
    ]

    ctx.complete(
        assets,
        result_metadata={
            "quality_checks": result.metadata.get("quality_checks"),
            "gpu_seconds": result.gpu_seconds,
            "peak_vram_mb": result.peak_vram_mb,
        },
    )


#: job type → task, used by the service layer when dispatching.
TASK_FOR_JOB_TYPE: dict[str, Any] = {
    "vton": run_vton_job,
    "background_remove": run_background_remove,
    "background_replace": run_background_replace,
    "product_photography": run_product_photography,
    "inpaint": run_inpaint,
    "object_remove": run_inpaint,
    "expand": run_expand,
    "upscale": run_upscale,
    "enhance": run_enhance,
}
