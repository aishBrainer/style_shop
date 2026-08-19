"""Diffusers-backed image generation and inpainting (§21, §23, §25, §26).

Powers backgrounds, product photography, generative fill and object removal
once real weights are installed. Requires torch + diffusers, which live only in
the GPU image.

Licensing note (§72): this adapter is model-agnostic, but the *checkpoint* you
point it at carries its own terms. SDXL ships under CreativeML Open RAIL++-M,
which permits commercial use but attaches use restrictions you must pass on to
your own users. Record whatever you install in MODEL_LICENSE.md before enabling.
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from app.ai.base import (
    GenerationResult,
    ImageGenerationEngine,
    ModelInfo,
    ProgressCallback,
    _noop_progress,
)
from app.ai.device import empty_cache, peak_vram_mb, reset_peak_vram, resolve_device
from app.core.config import settings
from app.core.errors import GPUOutOfMemoryError, ModelLoadError
from app.core.logging import get_logger
from app.models.enums import CommercialUse

log = get_logger(__name__)

DEFAULT_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
DEFAULT_INPAINT_MODEL = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"


class DiffusersImageGeneration(ImageGenerationEngine):
    info = ModelInfo(
        key="sdxl",
        name="SDXL (diffusers)",
        version="1.0",
        license="CreativeML Open RAIL++-M",
        license_url="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
        commercial_use=CommercialUse.UNREVIEWED,
        vram_requirement_mb=10240,
        framework="pytorch",
        notes="Confirm the checkpoint's terms and record them in MODEL_LICENSE.md.",
    )

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        inpaint_model_id: str = DEFAULT_INPAINT_MODEL,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.model_id = model_id
        self.inpaint_model_id = inpaint_model_id
        self.device = resolve_device()
        self._txt2img = None
        self._inpaint = None

    def load(self) -> None:
        try:
            import torch  # noqa: PLC0415
            from diffusers import (  # noqa: PLC0415
                AutoPipelineForInpainting,
                AutoPipelineForText2Image,
            )
        except ImportError as exc:
            raise ModelLoadError(
                "diffusers/torch are not installed in this image. Use the GPU "
                "image, or set IMAGE_PROVIDER=mock."
            ) from exc

        dtype = torch.float16 if self.device == "cuda" else torch.float32
        log.info("diffusers.loading", model=self.model_id, device=self.device)

        self._txt2img = AutoPipelineForText2Image.from_pretrained(
            self.model_id,
            torch_dtype=dtype,
            variant="fp16" if self.device == "cuda" else None,
            cache_dir=settings.ai_weights_dir,
        ).to(self.device)

        self._inpaint = AutoPipelineForInpainting.from_pretrained(
            self.inpaint_model_id,
            torch_dtype=dtype,
            cache_dir=settings.ai_weights_dir,
        ).to(self.device)

        # §52 — trades a little speed for a much lower VRAM ceiling, which is
        # what lets a 12 GB card serve this at all.
        for pipe in (self._txt2img, self._inpaint):
            pipe.enable_attention_slicing()
            if self.device == "cuda":
                pipe.enable_vae_tiling()

        self._loaded = True

    def unload(self) -> None:
        self._txt2img = None
        self._inpaint = None
        empty_cache()
        self._loaded = False

    def warmup(self) -> None:
        if self.device != "cuda" or self._txt2img is None:
            return
        try:
            self._txt2img("warmup", num_inference_steps=1, height=512, width=512)
        except Exception as exc:  # noqa: BLE001 — warmup failure is not fatal
            log.warning("diffusers.warmup_failed", error=str(exc))

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
    ) -> GenerationResult:
        import torch  # noqa: PLC0415

        if self._txt2img is None or self._inpaint is None:
            raise ModelLoadError("Diffusers pipelines are not loaded.")

        reset_peak_vram()
        generator = (
            torch.Generator(device=self.device).manual_seed(seed)
            if seed is not None
            else None
        )

        # diffusers reports step-by-step progress; map it onto our 15–90 band so
        # the UI bar tracks real denoising rather than a timer.
        def step_callback(_pipe, step: int, _t, cb_kwargs):
            on_progress(15 + int(75 * step / max(1, steps)), "Rendering image")
            return cb_kwargs

        common: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
            "num_images_per_prompt": num_images,
            "generator": generator,
            "callback_on_step_end": step_callback,
        }

        try:
            if init_image is not None and mask is not None:
                result = self._inpaint(
                    image=init_image.convert("RGB").resize((width, height)),
                    mask_image=mask.convert("L").resize((width, height)),
                    strength=strength,
                    height=height,
                    width=width,
                    **common,
                )
            else:
                result = self._txt2img(height=height, width=width, **common)
        except torch.cuda.OutOfMemoryError as exc:
            empty_cache()
            raise GPUOutOfMemoryError() from exc

        return GenerationResult(
            images=list(result.images),
            params={
                "model": self.model_id,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "width": width,
                "height": height,
                "strength": strength if init_image is not None else None,
            },
            peak_vram_mb=peak_vram_mb(),
        )
