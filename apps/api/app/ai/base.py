"""AI engine interfaces (§15, §70, §114).

Every engine is replaceable. Nothing above this layer — not the API, not the
services, and certainly not the frontend — may know which concrete model is
loaded. That is what makes "VTON v1 → VTON v2" a config change instead of a
rewrite.

Contract for implementers:

* `load()` is called once per worker process, not once per job (§51).
* `generate()` receives decoded PIL images and returns PIL images. Storage and
  the database are somebody else's problem.
* Report progress through the `on_progress` callback so the UI's live stages
  reflect real work rather than a fake timer.
* Raise the typed errors from `app.core.errors` — the worker maps those onto
  job error codes and user-safe messages.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from app.models.enums import CommercialUse, GarmentCategory

ProgressCallback = Callable[[int, str], None]


def _noop_progress(_percent: int, _label: str) -> None:
    pass


@dataclass(slots=True)
class ModelInfo:
    """Self-description used by the registry and the admin panel."""

    key: str
    name: str
    version: str = "1"
    license: str = "unknown"
    license_url: str | None = None
    commercial_use: CommercialUse = CommercialUse.UNREVIEWED
    vram_requirement_mb: int | None = None
    framework: str = "pytorch"
    notes: str | None = None


@dataclass(slots=True)
class GenerationResult:
    """What every engine returns. `images` is ordered; index 0 is primary."""

    images: list[Image.Image]
    params: dict[str, Any] = field(default_factory=dict)
    gpu_seconds: float | None = None
    peak_vram_mb: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AIEngine(ABC):
    """Common lifecycle for every engine kind."""

    info: ModelInfo

    def __init__(self, **options: Any) -> None:
        self.options = options
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def load(self) -> None:
        """Bring weights into memory. Called once at worker start-up (§51)."""

    def unload(self) -> None:
        """Release VRAM. Called on shutdown or when the registry evicts a model."""
        self._loaded = False

    def warmup(self) -> None:
        """Optional: run a tiny inference so the first real job is not the one
        that pays for kernel compilation (§52)."""

    def health(self) -> dict[str, Any]:
        return {"key": self.info.key, "loaded": self._loaded}


class VirtualTryOnEngine(AIEngine):
    """§15. The signature the spec asked for, with progress reporting added."""

    @abstractmethod
    def validate_input(self, person: Image.Image, garment: Image.Image) -> None:
        """Raise InvalidImageError if these two images cannot be processed."""

    @abstractmethod
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
    ) -> GenerationResult: ...


class SegmentationEngine(AIEngine):
    """Background removal and auto-masking (§13, §22). SAM 2 is the intended
    production implementation — Apache-2.0, so commercially usable (§72)."""

    @abstractmethod
    def segment(
        self,
        image: Image.Image,
        *,
        prompt_points: list[tuple[int, int]] | None = None,
        prompt_box: tuple[int, int, int, int] | None = None,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> Image.Image:
        """Return an L-mode mask: 255 = subject, 0 = background."""

    def cutout(self, image: Image.Image, **kwargs: Any) -> Image.Image:
        """RGBA with the background made transparent."""
        mask = self.segment(image, **kwargs)
        out = image.convert("RGBA")
        out.putalpha(mask.convert("L").resize(out.size, Image.Resampling.LANCZOS))
        return out


class ImageGenerationEngine(AIEngine):
    """Text-to-image and inpainting: backgrounds, product photography,
    generative fill, object removal (§21, §23, §25, §26)."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        init_image: Image.Image | None = None,
        mask: Image.Image | None = None,
        seed: int | None = None,
        steps: int = 30,
        guidance_scale: float = 7.0,
        strength: float = 0.85,
        width: int = 1024,
        height: int = 1024,
        num_images: int = 1,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> GenerationResult: ...


class UpscaleEngine(AIEngine):
    """§27 — independent worker so upscaling never blocks the try-on queue."""

    @abstractmethod
    def upscale(
        self,
        image: Image.Image,
        *,
        scale: int = 2,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> GenerationResult: ...


class VideoEngine(AIEngine):
    """§30 — image to short video. Pluggable by design; do not couple to one model."""

    @abstractmethod
    def animate(
        self,
        image: Image.Image,
        *,
        motion_preset: str = "slow_zoom",
        duration_seconds: float = 5.0,
        fps: int = 24,
        seed: int | None = None,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> bytes:
        """Return encoded MP4 bytes."""
