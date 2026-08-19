"""Virtual try-on pipeline — stages A–H of §17.

Pure orchestration: takes decoded images, walks the stages, returns images.
Storage, database writes and queue mechanics belong to the worker (§92).

    validate → preprocess → parse → pose → garment prep → VTON → post → output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageFilter

from app.ai.base import GenerationResult, ProgressCallback, _noop_progress
from app.ai.registry import get_segmentation_engine, get_vton_engine
from app.core.errors import InvalidImageError, OutputQualityError
from app.core.logging import get_logger
from app.models.enums import GarmentCategory
from app.services import imaging

log = get_logger(__name__)

# §93: the sizes the pipeline actually runs at. Larger costs VRAM roughly
# quadratically, so HD is a deliberate opt-in rather than a default.
STANDARD_SIZE = (768, 1024)
HD_SIZE = (1024, 1365)


@dataclass(slots=True)
class VTONRequest:
    person: Image.Image
    garment: Image.Image
    mask: Image.Image | None = None
    category: GarmentCategory = GarmentCategory.UPPER_BODY
    seed: int | None = None
    steps: int = 30
    guidance_scale: float = 2.0
    hd: bool = False
    num_images: int = 1
    auto_mask: bool = True
    preserve_face: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> tuple[int, int]:
        return HD_SIZE if self.hd else STANDARD_SIZE


def run_vton(
    request: VTONRequest,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    engine = get_vton_engine()

    # --- Stage A: input validation ----------------------------------------
    on_progress(4, "Checking your images")
    engine.validate_input(request.person, request.garment)
    _reject_unusable(request.person, request.garment)

    # --- Stage B: preprocessing -------------------------------------------
    on_progress(12, "Preparing images")
    width, height = request.size
    person = _normalise(request.person, (width, height))
    garment = _normalise(request.garment, (width, height), pad=True)

    # --- Stages C–E: parsing, pose, garment mask ---------------------------
    # With the mock/rembg providers there is no separate human-parsing or
    # DensePose model; segmentation stands in for the garment region. A real
    # VTON engine consumes parse maps and pose keypoints internally, which is
    # why they are not forced through this interface.
    mask = request.mask
    if mask is None and request.auto_mask:
        on_progress(22, "Detecting garment region")
        try:
            mask = get_segmentation_engine().segment(garment)
        except Exception as exc:  # noqa: BLE001 — auto-mask is best-effort
            log.warning("vton.automask_failed", error=str(exc))
            mask = None

    if mask is not None:
        mask = mask.convert("L").resize((width, height), Image.Resampling.LANCZOS)

    # --- Stage F: try-on ---------------------------------------------------
    def engine_progress(percent: int, label: str) -> None:
        # Compress the engine's 0–100 into the 30–85 band this stage owns.
        on_progress(30 + int(0.55 * percent), label)

    result = engine.generate(
        person,
        garment,
        mask,
        category=request.category,
        seed=request.seed,
        steps=request.steps,
        guidance_scale=request.guidance_scale,
        width=width,
        height=height,
        num_images=request.num_images,
        on_progress=engine_progress,
        **request.extra,
    )

    if not result.images:
        raise OutputQualityError("The model returned no image.")

    # --- Stage G: post-processing -----------------------------------------
    on_progress(88, "Rendering fabric")
    processed = [
        _postprocess(img, person, preserve_face=request.preserve_face)
        for img in result.images
    ]

    # --- Stage H: quality gate (§65) --------------------------------------
    on_progress(94, "Checking result quality")
    checks = _quality_checks(processed, (width, height))
    if not checks["passed"]:
        raise OutputQualityError(
            "The generated image did not pass quality checks.",
            details=checks,
        )

    result.images = processed
    result.metadata["quality_checks"] = checks
    return result


# ------------------------------------------------------------------ stages --

def _reject_unusable(person: Image.Image, garment: Image.Image) -> None:
    """Cheap pre-flight so an obviously bad upload fails in milliseconds rather
    than after a minute of GPU time."""
    if imaging.looks_blank(person):
        raise InvalidImageError(
            "The model image looks blank. Upload a photo with a visible person."
        )
    if imaging.looks_blank(garment):
        raise InvalidImageError(
            "The garment image looks blank. Upload a clear photo of the product."
        )


def _normalise(img: Image.Image, size: tuple[int, int], *, pad: bool = False) -> Image.Image:
    """Fit to the target size. Person images are cropped to fill; garments are
    padded so the product is never cut off."""
    rgb = img.convert("RGB")
    if not pad:
        return _crop_to_fill(rgb, size)

    fitted = imaging.fit_within(rgb, max(size))
    canvas = Image.new("RGB", size, (255, 255, 255))
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def _crop_to_fill(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_ratio = size[0] / size[1]
    ratio = img.width / img.height

    if ratio > target_ratio:  # too wide — trim the sides
        new_w = int(img.height * target_ratio)
        offset = (img.width - new_w) // 2
        box = (offset, 0, offset + new_w, img.height)
    else:  # too tall — trim from the bottom, keeping the head in frame
        new_h = int(img.width / target_ratio)
        box = (0, 0, img.width, new_h)

    return img.crop(box).resize(size, Image.Resampling.LANCZOS)


def _postprocess(
    generated: Image.Image, person: Image.Image, *, preserve_face: bool
) -> Image.Image:
    """§17 stage G: colour correction, face preservation, light sharpening."""
    out = generated.convert("RGB")
    if out.size != person.size:
        out = out.resize(person.size, Image.Resampling.LANCZOS)

    if preserve_face:
        out = _restore_face(out, person.convert("RGB"))

    return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))


def _restore_face(generated: Image.Image, person: Image.Image) -> Image.Image:
    """Paste the original head region back over the generated frame.

    Face degradation is the most common and most damaging try-on artefact, and
    the head is the one region no VTON model should be changing. The band is
    approximate (top ~18% of the frame) with a feathered edge — a face detector
    would be tighter, and is the obvious upgrade here.
    """
    band_h = int(person.height * 0.18)
    if band_h < 8:
        return generated

    mask = Image.new("L", person.size, 0)
    mask.paste(255, (0, 0, person.width, band_h))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=band_h * 0.22))

    return Image.composite(person, generated, mask)


def _quality_checks(images: list[Image.Image], expected: tuple[int, int]) -> dict[str, Any]:
    """§65 — automated checks before a result is ever shown to a user."""
    checks: dict[str, Any] = {
        "image_count": len(images),
        "blank_images": 0,
        "wrong_size": 0,
        "passed": True,
    }

    for img in images:
        if imaging.looks_blank(img):
            checks["blank_images"] += 1
        # Post-processing resizes back to the person's dimensions, so allow a
        # generous tolerance and only catch genuinely wrong output.
        if abs(img.width - expected[0]) > expected[0] * 0.5:
            checks["wrong_size"] += 1

    checks["passed"] = checks["blank_images"] == 0 and checks["wrong_size"] == 0
    return checks
