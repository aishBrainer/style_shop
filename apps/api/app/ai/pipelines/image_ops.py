"""Image studio pipelines (§21–§27).

Background removal/replacement, product photography, generative fill, object
removal, canvas expansion, enhancement and upscaling. Same contract as the VTON
pipeline: images in, images out, no I/O.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageFilter

from app.ai.base import GenerationResult, ProgressCallback, _noop_progress
from app.ai.registry import get_image_engine, get_segmentation_engine, get_upscale_engine
from app.core.errors import InvalidImageError
from app.services import imaging

# §21 / §23 presets. Stored here as the shipped defaults; the prompt_templates
# table (§68) is what the UI actually reads, seeded from these.
BACKGROUND_PRESETS: dict[str, str] = {
    "studio": "professional photography studio backdrop, soft even lighting, seamless paper",
    "white": "clean pure white seamless studio background, ecommerce product photography",
    "luxury": "luxury marble surface, warm sunlight, elegant minimal interior, editorial",
    "outdoor": "natural outdoor setting, soft daylight, shallow depth of field, bokeh",
    "minimal": "minimal neutral background, subtle gradient, soft shadow, clean composition",
    "gradient": "smooth colour gradient backdrop, modern studio lighting",
    "street": "urban street scene, natural light, blurred city background",
    "beach": "sunny beach, soft sand, ocean in the background, golden hour",
    "bedroom": "modern bedroom interior, soft natural window light, neutral tones",
    "office": "contemporary office interior, clean lines, soft daylight",
    "nature": "natural greenery, soft dappled sunlight, organic background",
    "runway": "fashion runway, dramatic spotlights, dark background, editorial",
}

LIGHTING_MODIFIERS: dict[str, str] = {
    "soft": "soft diffused lighting",
    "studio": "professional studio strobe lighting, controlled shadows",
    "dramatic": "dramatic directional lighting, deep shadows, high contrast",
    "natural": "natural daylight, gentle shadows",
    "editorial": "editorial fashion lighting, crisp highlights",
}

CAMERA_MODIFIERS: dict[str, str] = {
    "closeup": "close-up macro detail shot",
    "medium": "medium shot, balanced framing",
    "full": "full product in frame, generous margins",
    "hero": "hero shot, low angle, dramatic perspective",
}

COMPOSITION_MODIFIERS: dict[str, str] = {
    "center": "centred composition",
    "left": "subject positioned left of frame, copy space right",
    "right": "subject positioned right of frame, copy space left",
    "editorial": "off-centre editorial composition, negative space",
}

NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, watermark, text, logo, jpeg artifacts, "
    "extra limbs, deformed, oversaturated"
)


# --------------------------------------------------------------- §22 remove --

def remove_background(
    image: Image.Image,
    *,
    background: str = "transparent",
    background_color: str = "#FFFFFF",
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    """Returns RGBA when transparent, RGB otherwise."""
    on_progress(15, "Detecting subject")
    cutout = get_segmentation_engine().cutout(image, on_progress=on_progress)

    on_progress(80, "Compositing")
    if background == "transparent":
        out = cutout
    elif background == "color":
        out = imaging.composite_over_background(
            cutout, imaging.solid_background(cutout.size, background_color)
        )
    else:  # "white"
        out = imaging.composite_over_background(
            cutout, imaging.solid_background(cutout.size, "#FFFFFF")
        )

    on_progress(95, "Finishing image")
    return GenerationResult(
        images=[out],
        params={"background": background, "background_color": background_color},
    )


# -------------------------------------------------------------- §23 replace --

def replace_background(
    image: Image.Image,
    *,
    preset: str | None = None,
    prompt: str | None = None,
    seed: int | None = None,
    steps: int = 30,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    text = prompt or BACKGROUND_PRESETS.get(preset or "studio", BACKGROUND_PRESETS["studio"])

    on_progress(12, "Detecting subject")
    cutout = get_segmentation_engine().cutout(image)

    on_progress(30, "Generating background")
    generated = get_image_engine().generate(
        text,
        negative_prompt=NEGATIVE_PROMPT,
        seed=seed,
        steps=steps,
        width=_even(image.width),
        height=_even(image.height),
        on_progress=lambda p, label: on_progress(30 + int(0.5 * p), label),
    )

    on_progress(85, "Compositing")
    composited = imaging.composite_over_background(cutout, generated.images[0])

    on_progress(95, "Finishing image")
    return GenerationResult(
        images=[composited],
        params={**generated.params, "preset": preset, "prompt": text},
        peak_vram_mb=generated.peak_vram_mb,
    )


# --------------------------------------------------------- §21 photography --

def product_photography(
    image: Image.Image,
    *,
    background: str = "studio",
    lighting: str = "studio",
    camera: str = "medium",
    composition: str = "center",
    custom_prompt: str | None = None,
    seed: int | None = None,
    steps: int = 30,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    parts = [
        custom_prompt or BACKGROUND_PRESETS.get(background, BACKGROUND_PRESETS["studio"]),
        LIGHTING_MODIFIERS.get(lighting, ""),
        CAMERA_MODIFIERS.get(camera, ""),
        COMPOSITION_MODIFIERS.get(composition, ""),
        "professional ecommerce product photography, high detail, sharp focus",
    ]
    prompt = ", ".join(p for p in parts if p)

    result = replace_background(
        image, prompt=prompt, seed=seed, steps=steps, on_progress=on_progress
    )
    result.params.update(
        {
            "background": background,
            "lighting": lighting,
            "camera": camera,
            "composition": composition,
        }
    )
    return result


# ------------------------------------------------- §25 fill / §26 eraser ----

def inpaint(
    image: Image.Image,
    mask: Image.Image,
    *,
    prompt: str,
    seed: int | None = None,
    steps: int = 30,
    strength: float = 0.9,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    """Generative fill. `mask` white = the region to regenerate."""
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.Resampling.LANCZOS)

    return get_image_engine().generate(
        prompt,
        negative_prompt=NEGATIVE_PROMPT,
        init_image=image,
        mask=mask,
        seed=seed,
        steps=steps,
        strength=strength,
        width=_even(image.width),
        height=_even(image.height),
        on_progress=on_progress,
    )


def remove_object(
    image: Image.Image,
    mask: Image.Image,
    *,
    seed: int | None = None,
    steps: int = 30,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    """§26 magic eraser — inpaint the masked region with plausible background."""
    return inpaint(
        image,
        mask,
        prompt="clean empty background, seamless, natural continuation of the scene",
        seed=seed,
        steps=steps,
        strength=1.0,
        on_progress=on_progress,
    )


# ------------------------------------------------------------- §24 expand ---

def expand_canvas(
    image: Image.Image,
    *,
    left: int = 0,
    right: int = 0,
    top: int = 0,
    bottom: int = 0,
    prompt: str | None = None,
    seed: int | None = None,
    steps: int = 30,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    """Outpainting: grow the canvas and generate into the new area."""
    if max(left, right, top, bottom) <= 0:
        raise InvalidImageError("Specify at least one direction to expand.")

    new_w = image.width + left + right
    new_h = image.height + top + bottom
    if new_w > 4096 or new_h > 4096:
        raise InvalidImageError("The expanded canvas would exceed 4096px.")

    on_progress(15, "Preparing canvas")
    canvas = Image.new("RGB", (new_w, new_h), (128, 128, 128))
    canvas.paste(image.convert("RGB"), (left, top))

    # White = regenerate. Feathered so the seam blends instead of banding.
    mask = Image.new("L", (new_w, new_h), 255)
    mask.paste(0, (left, top, left + image.width, top + image.height))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=6))

    return inpaint(
        canvas,
        mask,
        prompt=prompt or "seamless natural continuation of the scene, matching lighting",
        seed=seed,
        steps=steps,
        strength=1.0,
        on_progress=lambda p, label: on_progress(15 + int(0.8 * p), label),
    )


# ------------------------------------------------------------ §27 upscale ---

def upscale(
    image: Image.Image,
    *,
    scale: int = 2,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    if scale not in (2, 4):
        raise InvalidImageError("Upscale factor must be 2x or 4x.")
    if image.width * scale > 8192 or image.height * scale > 8192:
        raise InvalidImageError(
            f"{scale}x would exceed 8192px. Try a smaller factor."
        )
    return get_upscale_engine().upscale(image, scale=scale, on_progress=on_progress)


# ------------------------------------------------------------ §24 enhance ---

def enhance(
    image: Image.Image,
    *,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
    blur: float = 0.0,
    auto: bool = False,
    on_progress: ProgressCallback = _noop_progress,
) -> GenerationResult:
    """Deterministic adjustments — no model involved, so this runs on the CPU
    queue and returns in well under a second."""
    on_progress(30, "Adjusting image")

    if auto:
        # Mild, safe defaults that flatter most ecommerce photography.
        brightness, contrast, saturation, sharpness = 1.04, 1.10, 1.06, 1.15

    out = imaging.adjust(
        image.convert("RGB"),
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        sharpness=sharpness,
        blur=blur,
    )

    on_progress(90, "Finishing image")
    return GenerationResult(
        images=[out],
        params={
            "brightness": brightness,
            "contrast": contrast,
            "saturation": saturation,
            "sharpness": sharpness,
            "blur": blur,
            "auto": auto,
        },
    )


def transform(
    image: Image.Image,
    *,
    crop: tuple[int, int, int, int] | None = None,
    resize: tuple[int, int] | None = None,
    rotate: int = 0,
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
    **_: Any,
) -> Image.Image:
    """§24 geometric edits. Synchronous — cheap enough not to need a job."""
    out = image
    if crop:
        out = out.crop(crop)
    if rotate:
        out = out.rotate(-rotate, expand=True, resample=Image.Resampling.BICUBIC)
    if flip_horizontal:
        out = out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_vertical:
        out = out.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if resize:
        out = out.resize(resize, Image.Resampling.LANCZOS)
    return out


def _even(value: int) -> int:
    """Diffusion models want dimensions divisible by 8."""
    return max(512, min(1536, (value // 8) * 8))
