"""CPU reference providers.

These are not toys that return the input unchanged. Each one does real image
work — compositing, colour transfer, procedural backgrounds, Lanczos upscaling
— so the entire product loop (queue → worker → progress → gallery → compare →
download) can be exercised and load-tested on a laptop with no GPU and no
model weights.

They are deterministic: the same seed yields the same output, which is what
makes §67 (seed management) and the test suite meaningful.

Swap them out by setting VTON_PROVIDER / IMAGE_PROVIDER / … in .env once a
licensed checkpoint is installed. Nothing above this file changes.
"""

from __future__ import annotations

import random
import time
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.ai.base import (
    GenerationResult,
    ImageGenerationEngine,
    ModelInfo,
    ProgressCallback,
    SegmentationEngine,
    UpscaleEngine,
    VideoEngine,
    VirtualTryOnEngine,
    _noop_progress,
)
from app.core.errors import InvalidImageError
from app.models.enums import CommercialUse, GarmentCategory

# Where on the body each category sits, as (top, bottom) fractions of height.
_CATEGORY_BANDS: dict[GarmentCategory, tuple[float, float]] = {
    GarmentCategory.UPPER_BODY: (0.18, 0.55),
    GarmentCategory.LOWER_BODY: (0.48, 0.90),
    GarmentCategory.FULL_BODY: (0.18, 0.92),
    GarmentCategory.DRESS: (0.20, 0.85),
    GarmentCategory.JUMPSUIT: (0.18, 0.90),
    GarmentCategory.OUTERWEAR: (0.15, 0.62),
    GarmentCategory.OTHER: (0.25, 0.70),
}


class MockVirtualTryOn(VirtualTryOnEngine):
    """Composites the garment onto the person's torso band.

    The result is obviously synthetic, and that is deliberate — it must never be
    mistaken for a real try-on. What it *is* good for: proving the pipeline end
    to end, generating gallery fixtures, and benchmarking queue throughput.
    """

    info = ModelInfo(
        key="mock",
        name="Mock Virtual Try-On (CPU reference)",
        version="1",
        license="MIT",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=0,
        framework="pillow",
        notes="Development placeholder. Produces a composite, not a real try-on.",
    )

    def load(self) -> None:
        self._loaded = True

    def validate_input(self, person: Image.Image, garment: Image.Image) -> None:
        if min(person.size) < 128:
            raise InvalidImageError("The model image is too small to work with.")
        if min(garment.size) < 64:
            raise InvalidImageError("The garment image is too small to work with.")

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
        started = time.monotonic()
        rng = random.Random(seed if seed is not None else 0)

        on_progress(10, "Preparing images")
        base = person.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)

        on_progress(30, "Locating garment region")
        region = self._region_for(category, width, height, mask)

        outputs: list[Image.Image] = []
        for i in range(max(1, num_images)):
            on_progress(
                40 + int(50 * i / max(1, num_images)),
                f"Applying garment ({i + 1}/{num_images})",
            )
            outputs.append(self._composite(base, garment, region, rng))

        on_progress(95, "Finishing image")
        return GenerationResult(
            images=outputs,
            params={
                "model": self.info.key,
                "steps": steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "width": width,
                "height": height,
                "category": str(category),
            },
            gpu_seconds=0.0,
            peak_vram_mb=0,
            metadata={"synthetic": True, "duration_s": round(time.monotonic() - started, 3)},
        )

    # ------------------------------------------------------------ internals --
    def _region_for(
        self,
        category: GarmentCategory,
        width: int,
        height: int,
        mask: Image.Image | None,
    ) -> tuple[int, int, int, int]:
        """Prefer the user's mask; fall back to the category's body band."""
        if mask is not None:
            box = mask.convert("L").getbbox()
            if box and (box[2] - box[0]) > 16 and (box[3] - box[1]) > 16:
                scaled = mask.convert("L").resize((width, height), Image.Resampling.NEAREST)
                box = scaled.getbbox()
                if box:
                    return box

        top_f, bottom_f = _CATEGORY_BANDS.get(category, (0.2, 0.6))
        band_h = int((bottom_f - top_f) * height)
        band_w = int(width * 0.62)
        left = (width - band_w) // 2
        return (left, int(top_f * height), left + band_w, int(top_f * height) + band_h)

    def _composite(
        self,
        base: Image.Image,
        garment: Image.Image,
        region: tuple[int, int, int, int],
        rng: random.Random,
    ) -> Image.Image:
        left, top, right, bottom = region
        rw, rh = max(1, right - left), max(1, bottom - top)

        g = garment.convert("RGBA")
        g = self._trim_flat_background(g)
        g = self._fit_into(g, rw, rh)

        # Soften the edge so the paste does not read as a hard rectangle.
        alpha = g.split()[3].filter(ImageFilter.GaussianBlur(radius=2.2))
        g.putalpha(alpha)

        out = base.convert("RGBA")
        # A pixel of positional jitter per output makes multi-image batches
        # visibly distinct instead of identical.
        jx, jy = rng.randint(-3, 3), rng.randint(-3, 3)
        paste_x = left + (rw - g.width) // 2 + jx
        paste_y = top + (rh - g.height) // 2 + jy
        out.alpha_composite(g, dest=(max(0, paste_x), max(0, paste_y)))

        return out.convert("RGB")

    @staticmethod
    def _trim_flat_background(img: Image.Image) -> Image.Image:
        """Knock out a uniform studio backdrop by sampling the corners.

        Cheap stand-in for real segmentation; good enough for packshots, which
        is what product uploads usually are.
        """
        arr = np.asarray(img.convert("RGBA"), dtype=np.int16)
        h, w = arr.shape[:2]
        corners = np.stack(
            [arr[0, 0, :3], arr[0, w - 1, :3], arr[h - 1, 0, :3], arr[h - 1, w - 1, :3]]
        ).astype(np.float32)

        # Corners disagreeing means the background is not flat — leave it alone.
        if corners.std(axis=0).mean() > 18:
            return img

        bg = corners.mean(axis=0)
        distance = np.sqrt(((arr[:, :, :3].astype(np.float32) - bg) ** 2).sum(axis=2))
        keep = distance >= 42

        # A garment that is itself close to the backdrop colour — or a flat
        # single-colour swatch — would otherwise be erased entirely, and the
        # composite would silently drop the product. Leave it alone instead.
        if keep.mean() < 0.05:
            return img

        arr[:, :, 3] = np.where(keep, arr[:, :, 3], 0)
        return Image.fromarray(arr.astype(np.uint8), mode="RGBA")

    @staticmethod
    def _fit_into(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
        scale = min(max_w / img.width, max_h / img.height)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        return img.resize(size, Image.Resampling.LANCZOS)


class MockSegmentation(SegmentationEngine):
    """Corner-sampled background keying. Real deployments use SAM 2 or rembg."""

    info = ModelInfo(
        key="mock",
        name="Mock Segmentation (CPU reference)",
        license="MIT",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=0,
        framework="numpy",
    )

    def load(self) -> None:
        self._loaded = True

    def segment(
        self,
        image: Image.Image,
        *,
        prompt_points: list[tuple[int, int]] | None = None,
        prompt_box: tuple[int, int, int, int] | None = None,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> Image.Image:
        on_progress(30, "Analysing image")

        if prompt_box:
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).rectangle(prompt_box, fill=255)
            on_progress(90, "Mask ready")
            return mask

        arr = np.asarray(image.convert("RGB"), dtype=np.float32)
        h, w = arr.shape[:2]
        bg = np.stack([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]]).mean(axis=0)
        distance = np.sqrt(((arr - bg) ** 2).sum(axis=2))

        on_progress(70, "Building mask")
        mask = np.where(distance > 40, 255, 0).astype(np.uint8)
        out = Image.fromarray(mask, mode="L").filter(ImageFilter.MedianFilter(size=5))
        on_progress(90, "Mask ready")
        return out


class MockImageGeneration(ImageGenerationEngine):
    """Procedural gradient/vignette backdrops seeded from the prompt text.

    The same prompt always produces the same backdrop, so preset thumbnails in
    the UI stay stable between runs.
    """

    info = ModelInfo(
        key="mock",
        name="Mock Image Generation (CPU reference)",
        license="MIT",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=0,
        framework="pillow",
    )

    def load(self) -> None:
        self._loaded = True

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
        started = time.monotonic()
        # Seed from the prompt when none given, so a preset is reproducible.
        effective_seed = seed if seed is not None else abs(hash(prompt)) % (2**31)
        rng = random.Random(effective_seed)

        outputs: list[Image.Image] = []
        for i in range(max(1, num_images)):
            on_progress(20 + int(60 * i / max(1, num_images)), "Rendering background")
            backdrop = self._backdrop(width, height, rng)

            if init_image is not None and mask is not None:
                # Inpainting: keep everything the mask marks as background.
                fg = init_image.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
                m = mask.convert("L").resize((width, height), Image.Resampling.LANCZOS)
                m = m.filter(ImageFilter.GaussianBlur(radius=2))
                fg.putalpha(m)
                backdrop = backdrop.convert("RGBA")
                backdrop.alpha_composite(fg)
                backdrop = backdrop.convert("RGB")
            elif init_image is not None:
                fg = init_image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
                backdrop = Image.blend(backdrop, fg, alpha=max(0.0, min(1.0, 1.0 - strength)))

            outputs.append(backdrop)

        on_progress(95, "Finishing image")
        return GenerationResult(
            images=outputs,
            params={
                "model": self.info.key,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": steps,
                "guidance_scale": guidance_scale,
                "seed": effective_seed,
                "width": width,
                "height": height,
            },
            gpu_seconds=0.0,
            peak_vram_mb=0,
            metadata={"synthetic": True, "duration_s": round(time.monotonic() - started, 3)},
        )

    @staticmethod
    def _backdrop(width: int, height: int, rng: random.Random) -> Image.Image:
        top = (rng.randint(30, 90), rng.randint(30, 90), rng.randint(40, 110))
        bottom = (rng.randint(140, 225), rng.randint(140, 225), rng.randint(150, 235))

        ys = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        grad = np.zeros((height, width, 3), dtype=np.float32)
        for c in range(3):
            grad[:, :, c] = top[c] * (1 - ys) + bottom[c] * ys

        # Radial vignette — reads as studio lighting rather than a flat ramp.
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        cx, cy = width * rng.uniform(0.35, 0.65), height * rng.uniform(0.25, 0.5)
        radius = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        falloff = 1.0 - 0.45 * (radius / radius.max())
        grad *= falloff[:, :, None]

        return Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8), mode="RGB").filter(
            ImageFilter.GaussianBlur(radius=1.5)
        )


class MockUpscale(UpscaleEngine):
    """Lanczos + unsharp mask. Genuinely useful as a fallback when no
    super-resolution weights are installed (§27)."""

    info = ModelInfo(
        key="mock",
        name="Lanczos Upscale (CPU reference)",
        license="MIT",
        commercial_use=CommercialUse.ALLOWED,
        vram_requirement_mb=0,
        framework="pillow",
    )

    def load(self) -> None:
        self._loaded = True

    def upscale(
        self,
        image: Image.Image,
        *,
        scale: int = 2,
        on_progress: ProgressCallback = _noop_progress,
        **kwargs: Any,
    ) -> GenerationResult:
        started = time.monotonic()
        on_progress(30, "Resampling")
        target = (image.width * scale, image.height * scale)
        out = image.convert("RGB").resize(target, Image.Resampling.LANCZOS)

        on_progress(75, "Sharpening")
        out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=115, threshold=3))

        on_progress(95, "Finishing image")
        return GenerationResult(
            images=[out],
            params={"model": self.info.key, "scale": scale},
            gpu_seconds=0.0,
            metadata={"duration_s": round(time.monotonic() - started, 3)},
        )


class MockVideo(VideoEngine):
    """Not implemented on CPU — video is Phase 2 (§30) and needs real weights.

    Present so the registry, queue routing and admin pages have something to
    resolve; raises a clear, user-safe error if actually invoked.
    """

    info = ModelInfo(
        key="mock",
        name="Mock Video (not implemented)",
        license="MIT",
        commercial_use=CommercialUse.ALLOWED,
        framework="none",
    )

    def load(self) -> None:
        self._loaded = True

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
        from app.core.errors import AIError

        raise AIError(
            "Video generation is not available yet.",
            code="FEATURE_NOT_IMPLEMENTED",
        )
