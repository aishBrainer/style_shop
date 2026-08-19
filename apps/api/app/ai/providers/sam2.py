"""SAM 2 auto-mask adapter (§13).

SAM 2 publishes code and checkpoints under Apache-2.0 (§72), so unlike the VTON
candidates it is safe for a commercial SaaS. It is the intended production
implementation of the mask editor's "Auto Mask" button: promptable with the
click points and boxes the user draws on the canvas.

Requires `sam2` + torch, which live only in the GPU image. With
SEGMENTATION_PROVIDER=rembg (the default) you get whole-subject cut-outs on
CPU; SAM 2 adds point/box-prompted region selection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.ai.base import ModelInfo, ProgressCallback, SegmentationEngine, _noop_progress
from app.ai.device import resolve_device
from app.core.config import settings
from app.core.errors import ModelLoadError
from app.core.logging import get_logger
from app.models.enums import CommercialUse

log = get_logger(__name__)

DEFAULT_CHECKPOINT = "sam2.1_hiera_large.pt"
DEFAULT_CONFIG = "configs/sam2.1/sam2.1_hiera_l.yaml"


class SAM2Segmentation(SegmentationEngine):
    info = ModelInfo(
        key="sam2",
        name="Segment Anything 2",
        version="2.1",
        license="Apache-2.0",
        license_url="https://github.com/facebookresearch/sam2",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=4096,
        framework="pytorch",
        notes="Promptable segmentation. Powers the mask editor's Auto Mask.",
    )

    def __init__(
        self,
        checkpoint: str = DEFAULT_CHECKPOINT,
        config: str = DEFAULT_CONFIG,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.device = resolve_device()
        self.checkpoint_path = Path(settings.ai_weights_dir) / "sam2" / checkpoint
        self.config = config
        self._predictor = None

    def load(self) -> None:
        try:
            from sam2.build_sam import build_sam2  # noqa: PLC0415
            from sam2.sam2_image_predictor import SAM2ImagePredictor  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError(
                "sam2 is not installed in this image. Use the GPU image, or set "
                "SEGMENTATION_PROVIDER=rembg."
            ) from exc

        if not self.checkpoint_path.exists():
            raise ModelLoadError(
                f"SAM 2 checkpoint missing at {self.checkpoint_path}. "
                f"Download it into AI_WEIGHTS_DIR/sam2/."
            )

        log.info("sam2.loading", checkpoint=str(self.checkpoint_path), device=self.device)
        model = build_sam2(self.config, str(self.checkpoint_path), device=self.device)
        self._predictor = SAM2ImagePredictor(model)
        self._loaded = True

    def unload(self) -> None:
        from app.ai.device import empty_cache  # noqa: PLC0415

        self._predictor = None
        empty_cache()
        self._loaded = False

    def segment(
        self,
        image: Image.Image,
        *,
        prompt_points: list[tuple[int, int]] | None = None,
        prompt_box: tuple[int, int, int, int] | None = None,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> Image.Image:
        if self._predictor is None:
            raise ModelLoadError("SAM 2 predictor is not loaded.")

        on_progress(20, "Encoding image")
        rgb = np.asarray(image.convert("RGB"))
        self._predictor.set_image(rgb)

        # No prompt: take the image centre, which is where a product photo's
        # subject virtually always sits.
        points = prompt_points or [(image.width // 2, image.height // 2)]
        point_coords = np.array(points, dtype=np.float32)
        point_labels = np.ones(len(points), dtype=np.int32)  # 1 = foreground

        on_progress(60, "Predicting mask")
        masks, scores, _ = self._predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            box=np.array(prompt_box, dtype=np.float32) if prompt_box else None,
            multimask_output=True,
        )

        best = masks[int(np.argmax(scores))]
        on_progress(90, "Mask ready")
        return Image.fromarray((best * 255).astype(np.uint8), mode="L")
