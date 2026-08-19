"""Pure image helpers shared by the API and the workers.

No database, no storage, no network — just bytes in, bytes out, so this module
is trivially testable and safe to call from either process type.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from app.core.errors import InvalidImageError, UploadRejectedError

# Pillow refuses images above this pixel count by default to blunt decompression
# bombs. We keep the guard and set our own, lower, explicit ceiling.
Image.MAX_IMAGE_PIXELS = 80_000_000

PREVIEW_MAX = 1024
THUMBNAIL_MAX = 400
MIN_DIMENSION = 256
MAX_DIMENSION = 8192


@dataclass(slots=True)
class ImageInfo:
    width: int
    height: int
    format: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str


def sniff(data: bytes) -> ImageInfo:
    """Identify an upload from its actual bytes.

    §58: never trust the browser's filename or Content-Type. Pillow parsing the
    header is the only thing that decides what this file is.
    """
    if not data:
        raise UploadRejectedError("The uploaded file is empty.")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # header integrity; consumes the file object
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            fmt = (img.format or "").upper()
    except UploadRejectedError:
        raise
    except Exception as exc:  # noqa: BLE001 — any decode failure is a rejection
        raise UploadRejectedError(
            "That file is not a readable image. Upload a JPG, PNG or WebP."
        ) from exc

    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(fmt)
    if mime is None:
        raise UploadRejectedError(
            f"{fmt or 'That file type'} is not supported. Use JPG, PNG or WebP."
        )

    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise UploadRejectedError(
            f"Image is too small ({width}x{height}). "
            f"Please upload at least {MIN_DIMENSION}x{MIN_DIMENSION} pixels."
        )
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise UploadRejectedError(
            f"Image is too large ({width}x{height}). "
            f"Maximum is {MAX_DIMENSION}x{MAX_DIMENSION} pixels."
        )

    return ImageInfo(
        width=width,
        height=height,
        format=fmt,
        mime_type=mime,
        size_bytes=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )


def load(data: bytes, *, mode: str = "RGB") -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        # Phone photos carry rotation in EXIF; bake it in so every downstream
        # stage sees the orientation the user saw.
        img = ImageOps.exif_transpose(img)
        return img.convert(mode)
    except Exception as exc:  # noqa: BLE001
        raise InvalidImageError("The image could not be decoded.") from exc


def encode(img: Image.Image, mime_type: str = "image/png", *, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    if mime_type == "image/jpeg":
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    elif mime_type == "image/webp":
        img.save(buf, format="WEBP", quality=quality, method=4)
    else:
        img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def fit_within(img: Image.Image, max_edge: int) -> Image.Image:
    """Downscale to fit a box, preserving aspect ratio. Never upscales."""
    if max(img.size) <= max_edge:
        return img.copy()
    out = img.copy()
    out.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return out


def make_renditions(data: bytes) -> tuple[bytes, bytes]:
    """(preview, thumbnail) as WebP — §98, so the gallery never loads originals."""
    img = load(data)
    preview = encode(fit_within(img, PREVIEW_MAX), "image/webp", quality=82)
    thumbnail = encode(fit_within(img, THUMBNAIL_MAX), "image/webp", quality=75)
    return preview, thumbnail


def apply_watermark(img: Image.Image, text: str = "AI Fashion Studio") -> Image.Image:
    """§4.2 — free-tier downloads are watermarked."""
    out = img.convert("RGBA")
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(16, out.width // 28)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = max(12, out.width // 60)
    pos = (out.width - tw - margin, out.height - th - margin * 2)

    draw.text((pos[0] + 2, pos[1] + 2), text, font=font, fill=(0, 0, 0, 90))
    draw.text(pos, text, font=font, fill=(255, 255, 255, 165))

    return Image.alpha_composite(out, overlay).convert("RGB")


# ------------------------------------------------------------ enhancements --

def adjust(
    img: Image.Image,
    *,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
    blur: float = 0.0,
) -> Image.Image:
    out = img
    if brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(brightness)
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    if saturation != 1.0:
        out = ImageEnhance.Color(out).enhance(saturation)
    if sharpness != 1.0:
        out = ImageEnhance.Sharpness(out).enhance(sharpness)
    if blur > 0:
        out = out.filter(ImageFilter.GaussianBlur(radius=blur))
    return out


def composite_over_background(
    foreground_rgba: Image.Image, background: Image.Image
) -> Image.Image:
    """Place a cut-out over a background, matching the foreground's size."""
    bg = background.convert("RGB").resize(foreground_rgba.size, Image.Resampling.LANCZOS)
    bg.paste(foreground_rgba, (0, 0), foreground_rgba)
    return bg


def solid_background(size: tuple[int, int], color: str = "#FFFFFF") -> Image.Image:
    return Image.new("RGB", size, color)


# -------------------------------------------------------- quality checking --

def looks_blank(img: Image.Image, *, std_threshold: float = 3.0) -> bool:
    """§65 — near-uniform output means the model produced nothing useful."""
    import numpy as np

    arr = np.asarray(img.convert("L"), dtype="float32")
    return bool(arr.std() < std_threshold)


def is_corrupt(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
        return False
    except Exception:  # noqa: BLE001
        return True
