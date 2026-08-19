"""Background removal via rembg / U²-Net (§22).

Real segmentation that runs on CPU, so background removal works from day one
without a GPU. Weights download on first use into AI_WEIGHTS_DIR.

Licensing: rembg is MIT; the default u2net checkpoint is Apache-2.0. Both
permit commercial use — verify against MODEL_LICENSE.md if you change models.
"""

from __future__ import annotations

import io
import os
from typing import Any

from PIL import Image

from app.ai.base import ModelInfo, ProgressCallback, SegmentationEngine, _noop_progress
from app.core.config import settings
from app.core.errors import ModelLoadError
from app.core.logging import get_logger
from app.models.enums import CommercialUse

log = get_logger(__name__)


class RembgSegmentation(SegmentationEngine):
    info = ModelInfo(
        key="rembg",
        name="rembg / U²-Net",
        version="2",
        license="MIT (code) + Apache-2.0 (u2net weights)",
        license_url="https://github.com/danielgatis/rembg",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=0,
        framework="onnxruntime",
        notes="CPU inference. First run downloads ~176 MB of weights.",
    )

    def __init__(self, model_name: str = "u2net", **options: Any) -> None:
        super().__init__(**options)
        self.model_name = model_name
        self._session = None

    def load(self) -> None:
        # rembg caches weights under U2NET_HOME; point it at our volume so a
        # container restart does not re-download them.
        os.environ.setdefault("U2NET_HOME", settings.ai_weights_dir)
        try:
            from rembg import new_session  # noqa: PLC0415
        except ImportError as exc:
            raise ModelLoadError(
                "rembg is not installed in this image. Set SEGMENTATION_PROVIDER=mock "
                "or add rembg to requirements."
            ) from exc

        log.info("rembg.loading", model=self.model_name)
        self._session = new_session(self.model_name)
        self._loaded = True

    def unload(self) -> None:
        self._session = None
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
        from rembg import remove  # noqa: PLC0415

        on_progress(25, "Detecting subject")
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")

        cut = remove(buf.getvalue(), session=self._session)
        on_progress(80, "Refining edges")

        with Image.open(io.BytesIO(cut)) as rgba:
            mask = rgba.convert("RGBA").split()[3].copy()

        on_progress(95, "Mask ready")
        return mask

    def cutout(self, image: Image.Image, **kwargs: Any) -> Image.Image:
        """Override: rembg already produces an alpha matte, so going through a
        binary mask would throw away the soft edges it computed."""
        from rembg import remove  # noqa: PLC0415

        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        cut = remove(buf.getvalue(), session=self._session)
        with Image.open(io.BytesIO(cut)) as img:
            return img.convert("RGBA").copy()
