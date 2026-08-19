"""Engine registry and per-process model cache (§50, §51, §52).

Two responsibilities:

1. Map a provider key ("mock", "catvton", …) to a class, without the caller
   importing the implementation — importing a torch-backed module at API
   start-up would pull CUDA into a process that has no business with it.
2. Keep one loaded instance per worker process so weights are loaded once and
   stay in VRAM (§51), with an explicit eviction path (§52).
"""

from __future__ import annotations

import importlib
import threading
from typing import Any

from app.ai.base import (
    AIEngine,
    ImageGenerationEngine,
    SegmentationEngine,
    UpscaleEngine,
    VideoEngine,
    VirtualTryOnEngine,
)
from app.core.config import settings
from app.core.errors import LicenseError, ModelLoadError
from app.core.logging import get_logger
from app.models.enums import AIModelType, CommercialUse

log = get_logger(__name__)

#: provider key -> "module.path:ClassName". Lazily imported.
PROVIDERS: dict[AIModelType, dict[str, str]] = {
    AIModelType.VTON: {
        "mock": "app.ai.providers.mock:MockVirtualTryOn",
        # Non-commercial (CC BY-NC-SA 4.0). Blocked unless explicitly allowed —
        # see MODEL_LICENSE.md before touching this.
        "catvton": "app.ai.providers.catvton:CatVTONEngine",
    },
    AIModelType.SEGMENTATION: {
        "mock": "app.ai.providers.mock:MockSegmentation",
        "rembg": "app.ai.providers.rembg_provider:RembgSegmentation",
        "sam2": "app.ai.providers.sam2:SAM2Segmentation",
    },
    AIModelType.IMAGE_GENERATION: {
        "mock": "app.ai.providers.mock:MockImageGeneration",
        "sdxl": "app.ai.providers.diffusers_provider:DiffusersImageGeneration",
    },
    AIModelType.UPSCALE: {
        "mock": "app.ai.providers.mock:MockUpscale",
        "realesrgan": "app.ai.providers.realesrgan:RealESRGANUpscale",
    },
    AIModelType.VIDEO: {
        "mock": "app.ai.providers.mock:MockVideo",
    },
}

#: Which env setting selects the provider for each engine kind.
_SETTING_FOR_TYPE: dict[AIModelType, str] = {
    AIModelType.VTON: "vton_provider",
    AIModelType.SEGMENTATION: "segmentation_provider",
    AIModelType.IMAGE_GENERATION: "image_provider",
    AIModelType.UPSCALE: "upscale_provider",
    AIModelType.VIDEO: "video_provider",
}

_BASE_FOR_TYPE: dict[AIModelType, type[AIEngine]] = {
    AIModelType.VTON: VirtualTryOnEngine,
    AIModelType.SEGMENTATION: SegmentationEngine,
    AIModelType.IMAGE_GENERATION: ImageGenerationEngine,
    AIModelType.UPSCALE: UpscaleEngine,
    AIModelType.VIDEO: VideoEngine,
}

_cache: dict[str, AIEngine] = {}
_cache_lock = threading.Lock()


def configured_provider(engine_type: AIModelType) -> str:
    return getattr(settings, _SETTING_FOR_TYPE[engine_type])


def resolve_class(engine_type: AIModelType, provider_key: str) -> type[AIEngine]:
    try:
        path = PROVIDERS[engine_type][provider_key]
    except KeyError as exc:
        known = ", ".join(sorted(PROVIDERS.get(engine_type, {})))
        raise ModelLoadError(
            f"No {engine_type} provider registered under {provider_key!r}. Known: {known}."
        ) from exc

    module_path, _, class_name = path.partition(":")
    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise ModelLoadError(
            f"Provider {provider_key!r} is registered but could not be imported "
            f"({exc}). Its dependencies are probably missing from this image."
        ) from exc

    expected = _BASE_FOR_TYPE[engine_type]
    if not issubclass(cls, expected):
        raise ModelLoadError(
            f"{class_name} does not implement {expected.__name__}."
        )
    return cls


def get_engine(
    engine_type: AIModelType,
    provider_key: str | None = None,
    **options: Any,
) -> AIEngine:
    """Return a loaded engine, reusing the process-wide instance when possible.

    Thread-safe: two Celery threads asking for the same engine at once must not
    both pay for loading it.
    """
    key = provider_key or configured_provider(engine_type)
    cache_key = f"{engine_type}:{key}"

    cached = _cache.get(cache_key)
    if cached is not None and cached.is_loaded:
        return cached

    with _cache_lock:
        # Re-check: another thread may have loaded it while we waited.
        cached = _cache.get(cache_key)
        if cached is not None and cached.is_loaded:
            return cached

        cls = resolve_class(engine_type, key)
        engine = cls(**options)
        _enforce_license(engine)

        log.info("ai.loading_engine", engine_type=str(engine_type), provider=key)
        try:
            engine.load()
        except Exception as exc:  # noqa: BLE001
            log.error(
                "ai.load_failed", engine_type=str(engine_type), provider=key, error=str(exc)
            )
            raise ModelLoadError(f"Could not load {key}: {exc}") from exc

        engine.warmup()
        _cache[cache_key] = engine
        log.info(
            "ai.engine_ready",
            engine_type=str(engine_type),
            provider=key,
            license=engine.info.license,
        )
        return engine


def _enforce_license(engine: AIEngine) -> None:
    """§72 — a non-commercial checkpoint must never load by accident."""
    if engine.info.commercial_use == CommercialUse.ALLOWED:
        return
    if settings.allow_non_commercial_models:
        log.warning(
            "ai.non_commercial_model_allowed",
            provider=engine.info.key,
            license=engine.info.license,
            hint="ALLOW_NON_COMMERCIAL_MODELS=true — do not run this in production.",
        )
        return
    raise LicenseError(
        f"{engine.info.name} is licensed {engine.info.license}, which does not "
        f"clearly permit commercial use. Set ALLOW_NON_COMMERCIAL_MODELS=true "
        f"for local evaluation only, or pick a different provider. "
        f"See MODEL_LICENSE.md."
    )


def unload_all() -> None:
    """§52 — called on worker shutdown to free VRAM deterministically."""
    with _cache_lock:
        for cache_key, engine in list(_cache.items()):
            try:
                engine.unload()
            except Exception as exc:  # noqa: BLE001
                log.warning("ai.unload_failed", engine=cache_key, error=str(exc))
            _cache.pop(cache_key, None)


def loaded_engines() -> list[str]:
    return sorted(k for k, v in _cache.items() if v.is_loaded)


# --- typed convenience accessors ------------------------------------------

def get_vton_engine(**opts: Any) -> VirtualTryOnEngine:
    return get_engine(AIModelType.VTON, **opts)  # type: ignore[return-value]


def get_segmentation_engine(**opts: Any) -> SegmentationEngine:
    return get_engine(AIModelType.SEGMENTATION, **opts)  # type: ignore[return-value]


def get_image_engine(**opts: Any) -> ImageGenerationEngine:
    return get_engine(AIModelType.IMAGE_GENERATION, **opts)  # type: ignore[return-value]


def get_upscale_engine(**opts: Any) -> UpscaleEngine:
    return get_engine(AIModelType.UPSCALE, **opts)  # type: ignore[return-value]


def get_video_engine(**opts: Any) -> VideoEngine:
    return get_engine(AIModelType.VIDEO, **opts)  # type: ignore[return-value]
