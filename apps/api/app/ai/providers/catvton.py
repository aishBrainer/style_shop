"""CatVTON adapter — NOT DEPLOYABLE AS-IS.

CatVTON publishes under CC BY-NC-SA 4.0 (§16, §72). That licence forbids
commercial use, which is exactly what a paid SaaS is. The registry therefore
refuses to load this engine unless ALLOW_NON_COMMERCIAL_MODELS=true, and that
flag exists for local benchmarking only.

Keep this file for one reason: benchmarking (§78). Run it against your fixed
evaluation set, record generation time / VRAM / quality, and use those numbers
to judge whichever commercially-licensed model you eventually pick. Do not
ship it.

Implementation is left as a stub because it depends on which CatVTON release
you vendor and where the checkpoint lands. Fill in `load` and `generate` after
the licence review clears — or delete the file if you go another way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from app.ai.base import (
    GenerationResult,
    ModelInfo,
    ProgressCallback,
    VirtualTryOnEngine,
    _noop_progress,
)
from app.ai.device import empty_cache, peak_vram_mb, reset_peak_vram, resolve_device
from app.core.config import settings
from app.core.errors import InvalidImageError, ModelLoadError
from app.core.logging import get_logger
from app.models.enums import CommercialUse, GarmentCategory

log = get_logger(__name__)


class CatVTONEngine(VirtualTryOnEngine):
    info = ModelInfo(
        key="catvton",
        name="CatVTON",
        version="1",
        license="CC BY-NC-SA 4.0",
        license_url="https://github.com/Zheng-Chong/CatVTON",
        commercial_use=CommercialUse.NOT_ALLOWED,
        vram_requirement_mb=8192,
        framework="pytorch",
        notes=(
            "Non-commercial licence. Benchmarking only — see MODEL_LICENSE.md. "
            "Authors report inference under 8 GB VRAM at 1024x768."
        ),
    )

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self.device = resolve_device()
        self.weights_dir = Path(settings.ai_weights_dir) / "catvton"
        self._pipeline = None

    def load(self) -> None:
        if not self.weights_dir.exists():
            raise ModelLoadError(
                f"CatVTON weights not found at {self.weights_dir}. Download them "
                f"into AI_WEIGHTS_DIR first — and confirm the licence permits "
                f"your use before you do."
            )
        raise ModelLoadError(
            "The CatVTON adapter is a stub. Implement load()/generate() against "
            "the release you vendored before enabling this provider."
        )

    def unload(self) -> None:
        self._pipeline = None
        empty_cache()
        self._loaded = False

    def validate_input(self, person: Image.Image, garment: Image.Image) -> None:
        if min(person.size) < 256:
            raise InvalidImageError(
                "The model image is too small. Use at least 256px on the short edge."
            )
        if min(garment.size) < 256:
            raise InvalidImageError("The garment image is too small.")

    def generate(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image | None = None,
        *,
        category: GarmentCategory = GarmentCategory.UPPER_BODY,
        seed: int | None = None,
        steps: int = 30,
        guidance_scale: float = 2.0,
        width: int = 768,
        height: int = 1024,
        num_images: int = 1,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> GenerationResult:
        # Reference shape for whoever implements this. The surrounding
        # bookkeeping — progress reporting, VRAM accounting, param capture — is
        # what the worker and §66 expect from any VTON engine.
        raise ModelLoadError("CatVTON adapter is not implemented.")

        reset_peak_vram()  # noqa: W0101 — retained as the intended template
        on_progress(15, "Preparing images")
        # images = self._pipeline(person, garment, mask, ...).images
        # on_progress(90, "Rendering fabric")
        return GenerationResult(
            images=[],
            params={
                "model": self.info.key,
                "steps": steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "width": width,
                "height": height,
                "category": str(category),
            },
            peak_vram_mb=peak_vram_mb(),
        )
