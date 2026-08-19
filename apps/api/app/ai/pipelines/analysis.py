"""Product analysis (§10 step 2) and custom model validation (§12).

Both run on the CPU queue immediately after upload, so the studio can show the
detected category and a warning about an unusable model photo before the user
spends a credit.

Category detection here is a heuristic on aspect ratio and the mask's vertical
distribution, not a trained classifier. It is right often enough to pre-select
the correct option, and the user can always override it — which is the correct
trade-off before there is training data to fit a real classifier on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from app.ai.registry import get_segmentation_engine
from app.core.logging import get_logger
from app.models.enums import GarmentCategory

log = get_logger(__name__)


@dataclass(slots=True)
class ProductAnalysis:
    category: GarmentCategory
    confidence: float
    bounding_box: list[int]
    mask: Image.Image | None = None
    details: dict[str, Any] = field(default_factory=dict)


def analyse_product(image: Image.Image) -> ProductAnalysis:
    rgb = image.convert("RGB")

    try:
        mask = get_segmentation_engine().segment(rgb)
    except Exception as exc:  # noqa: BLE001 — analysis must never block upload
        log.warning("analysis.segmentation_failed", error=str(exc))
        return ProductAnalysis(
            category=GarmentCategory.UPPER_BODY,
            confidence=0.0,
            bounding_box=[0, 0, rgb.width, rgb.height],
            details={"segmentation": "unavailable"},
        )

    box = mask.getbbox() or (0, 0, rgb.width, rgb.height)
    x0, y0, x1, y1 = box
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    aspect = w / h

    arr = np.asarray(mask.convert("L"), dtype=np.float32) / 255.0
    category, confidence = _classify(arr, aspect, box, rgb.size)

    return ProductAnalysis(
        category=category,
        confidence=confidence,
        bounding_box=[x0, y0, w, h],
        mask=mask,
        details={
            "aspect_ratio": round(aspect, 3),
            "coverage": round(float(arr.mean()), 3),
            "method": "heuristic",
        },
    )


def _classify(
    mask: np.ndarray, aspect: float, box: tuple[int, int, int, int], size: tuple[int, int]
) -> tuple[GarmentCategory, float]:
    """Shape heuristics, ordered from most to least distinctive.

    A dress/jumpsuit is tall and narrow; trousers are tall but split into two
    legs low down; a shirt is roughly square or wider than tall.
    """
    height = mask.shape[0]
    rows = mask.sum(axis=1)
    total = rows.sum() or 1.0

    top_third = rows[: height // 3].sum() / total
    bottom_third = rows[2 * height // 3 :].sum() / total

    # Two separated blobs across the lower rows = legs.
    lower = mask[int(height * 0.7) :]
    split = _has_vertical_split(lower)

    if aspect < 0.55 and bottom_third > 0.28:
        return (GarmentCategory.LOWER_BODY, 0.6) if split else (GarmentCategory.DRESS, 0.55)
    if aspect < 0.75:
        return (GarmentCategory.LOWER_BODY, 0.55) if split else (GarmentCategory.FULL_BODY, 0.5)
    if aspect > 1.25 and top_third > 0.3:
        return GarmentCategory.UPPER_BODY, 0.7

    return GarmentCategory.UPPER_BODY, 0.45


def _has_vertical_split(region: np.ndarray) -> bool:
    if region.size == 0:
        return False
    columns = region.sum(axis=0)
    if columns.max() == 0:
        return False
    occupied = columns > columns.max() * 0.2
    # Count runs of occupied columns; two runs means two legs.
    runs = int(np.sum(np.diff(occupied.astype(int)) == 1)) + int(occupied[0])
    return runs >= 2


# ---------------------------------------------------------- §12 validation --

@dataclass(slots=True)
class ModelValidation:
    acceptable: bool
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    #: Copy the spec asks for verbatim when a photo is unusable.
    REJECTION_MESSAGE = (
        "Please upload a full-body or 3/4-body image with the subject clearly visible."
    )


def validate_model_image(image: Image.Image) -> ModelValidation:
    """Checks a custom model upload for the things that break try-on.

    Deliberately no face *recognition* — only presence/coverage checks. §102 and
    §103: we are not building a biometric database out of customer uploads.
    """
    rgb = image.convert("RGB")
    reasons: list[str] = []
    details: dict[str, Any] = {}

    # Portrait framing. A landscape photo is almost never a usable full body.
    aspect = rgb.width / rgb.height
    details["aspect_ratio"] = round(aspect, 3)
    if aspect > 1.1:
        reasons.append("The photo is landscape; a portrait full-body shot works far better.")

    # Resolution.
    details["size"] = [rgb.width, rgb.height]
    if min(rgb.size) < 512:
        reasons.append("The image is low resolution. Use at least 512px on the short edge.")

    # Sharpness, via variance of the Laplacian — the standard cheap blur test.
    sharpness = _laplacian_variance(rgb)
    details["sharpness"] = round(sharpness, 2)
    if sharpness < 45:
        reasons.append("The photo looks blurry or out of focus.")

    # Subject coverage: too little means the person is lost in the frame; too
    # much means it is a crop rather than a full body.
    try:
        mask = get_segmentation_engine().segment(rgb)
        arr = np.asarray(mask.convert("L"), dtype=np.float32) / 255.0
        coverage = float(arr.mean())
        details["subject_coverage"] = round(coverage, 3)

        if coverage < 0.08:
            reasons.append("No clear subject was detected in the photo.")
        elif coverage > 0.85:
            reasons.append("The subject fills the frame; leave some space around them.")
        else:
            box = mask.getbbox()
            if box:
                subject_h = (box[3] - box[1]) / rgb.height
                details["subject_height_ratio"] = round(subject_h, 3)
                if subject_h < 0.45:
                    reasons.append("The subject is too small in the frame.")
    except Exception as exc:  # noqa: BLE001
        log.warning("validation.segmentation_failed", error=str(exc))
        details["segmentation"] = "unavailable"

    return ModelValidation(acceptable=not reasons, reasons=reasons, details=details)


def _laplacian_variance(img: Image.Image) -> float:
    import cv2  # noqa: PLC0415

    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
