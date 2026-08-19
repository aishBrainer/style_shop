"""Real-ESRGAN super-resolution (§27).

Real-ESRGAN is BSD-3-Clause, so it is safe for commercial use — one of the few
AI components in this stack where licensing is not a live question. Its weights
live in AI_WEIGHTS_DIR and it runs as its own worker so a 4x upscale never
blocks the try-on queue.

Falls back to nothing: if the dependency is absent, keep UPSCALE_PROVIDER=mock,
which does Lanczos + unsharp and is perfectly serviceable for 2x.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.ai.base import (
    GenerationResult,
    ModelInfo,
    ProgressCallback,
    UpscaleEngine,
    _noop_progress,
)
from app.ai.device import empty_cache, peak_vram_mb, reset_peak_vram, resolve_device
from app.core.config import settings
from app.core.errors import GPUOutOfMemoryError, ModelLoadError
from app.core.logging import get_logger
from app.models.enums import CommercialUse

log = get_logger(__name__)


class RealESRGANUpscale(UpscaleEngine):
    info = ModelInfo(
        key="realesrgan",
        name="Real-ESRGAN x4plus",
        version="0.3",
        license="BSD-3-Clause",
        license_url="https://github.com/xinntao/Real-ESRGAN",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=2048,
        framework="pytorch",
    )

    def __init__(self, weights: str = "RealESRGAN_x4plus.pth", **options: Any) -> None:
        super().__init__(**options)
        self.device = resolve_device()
        self.weights_path = Path(settings.ai_weights_dir) / "realesrgan" / weights
        self._upsampler = None

    def load(self) -> None:
        try:
            from basicsr.archs.rrdbnet_arch import RRDBNet  # noqa: PLC0415
            from realesrgan import RealESRGANer  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError(
                "realesrgan is not installed in this image. Set UPSCALE_PROVIDER=mock "
                "for Lanczos upscaling instead."
            ) from exc

        if not self.weights_path.exists():
            raise ModelLoadError(f"Real-ESRGAN weights missing at {self.weights_path}.")

        model = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
        )
        self._upsampler = RealESRGANer(
            scale=4,
            model_path=str(self.weights_path),
            model=model,
            # Tiling keeps peak VRAM bounded regardless of input size — without
            # it, a 4000px input OOMs a 24 GB card.
            tile=512,
            tile_pad=10,
            half=self.device == "cuda",
            device=self.device,
        )
        self._loaded = True

    def unload(self) -> None:
        self._upsampler = None
        empty_cache()
        self._loaded = False

    def upscale(
        self,
        image: Image.Image,
        *,
        scale: int = 2,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> GenerationResult:
        if self._upsampler is None:
            raise ModelLoadError("Real-ESRGAN is not loaded.")

        reset_peak_vram()
        on_progress(25, "Upscaling")

        bgr = np.asarray(image.convert("RGB"))[:, :, ::-1]
        try:
            output, _ = self._upsampler.enhance(bgr, outscale=scale)
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                empty_cache()
                raise GPUOutOfMemoryError() from exc
            raise

        on_progress(90, "Finishing image")
        return GenerationResult(
            images=[Image.fromarray(output[:, :, ::-1])],
            params={"model": self.info.key, "scale": scale},
            peak_vram_mb=peak_vram_mb(),
        )
