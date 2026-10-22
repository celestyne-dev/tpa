"""Image validation and optimisation (Pillow).

Pipeline for every upload:

1. Size limit, then content sniffing (the declared type and extension are ignored).
2. Header-only dimension and pixel-count checks before decoding (decompression
   bombs), a full ``verify()`` pass, and rejection of animated images and SVG.
3. EXIF orientation applied, ICC profiles converted to sRGB, CMYK/palette
   images normalised, transparency kept only when actually used.
4. Responsive derivatives in WebP (lossy or lossless, whichever suits the
   content), AVIF only when it is smaller *and* not visibly worse, plus a
   JPEG/PNG fallback. Never upscaled. Metadata (EXIF/GPS/XMP) is never written
   to public derivatives.
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
import warnings
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageCms, ImageOps, ImageStat, features

SUPPORTED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
if features.check("avif"):
    SUPPORTED_FORMATS["AVIF"] = "image/avif"

RESPONSIVE_WIDTHS = (160, 320, 640, 960, 1280, 1600)
MIME = {"webp": "image/webp", "avif": "image/avif", "jpeg": "image/jpeg", "png": "image/png"}
EXT = {"webp": "webp", "avif": "avif", "jpeg": "jpg", "png": "png"}


class ImageRejected(ValueError):
    """The upload is not an acceptable image. The message is safe to show users."""


@dataclass(frozen=True)
class Preset:
    """How an image is prepared for one kind of use.

    ``mode="derived"`` presets reuse the responsive set and are cropped in the
    browser (CSS aspect-ratio + object-position at the focal point), so no extra
    files are stored. ``mode="cropped"`` presets get their own files.
    """

    name: str
    label: str
    aspect: float | None  # width / height; None keeps the original aspect
    max_width: int
    quality: int  # WebP quality for photographs
    target_kb: tuple[int, int]  # optimisation target for the typical display size
    mode: str = "derived"
    widths: tuple[int, ...] = ()
    on_upload: bool = False
    sizes: str = "100vw"


PRESETS: dict[str, Preset] = {
    p.name: p
    for p in (
        Preset(
            "responsive",
            "Responsive (original aspect)",
            None,
            1600,
            80,
            (60, 180),
            mode="cropped",
            widths=RESPONSIVE_WIDTHS,
            on_upload=True,
            sizes="(min-width: 768px) 720px, 100vw",
        ),
        Preset(
            "thumbnail",
            "Article thumbnail",
            16 / 10,
            640,
            76,
            (20, 80),
            sizes="(min-width: 1024px) 360px, (min-width: 640px) 50vw, 100vw",
        ),
        Preset("featured", "Featured article image", 16 / 10, 1600, 80, (60, 180)),
        Preset("homepage", "Homepage banner", 21 / 9, 1600, 80, (80, 250)),
        Preset(
            "avatar",
            "Author portrait",
            1.0,
            640,
            78,
            (15, 50),
            mode="cropped",
            widths=(160, 320, 640),
            on_upload=True,
            sizes="96px",
        ),
        Preset(
            "social",
            "Social sharing (1200x630)",
            1200 / 630,
            1200,
            82,
            (60, 200),
            mode="cropped",
            widths=(1200,),
            on_upload=True,
        ),
        Preset(
            "ebook_cover",
            "eBook cover (2:3, future)",
            2 / 3,
            1200,
            82,
            (40, 160),
            mode="cropped",
            widths=(400, 800, 1200),
            sizes="(min-width: 768px) 320px, 60vw",
        ),
    )
}


@dataclass
class EncodedFile:
    preset: str
    format: str
    width: int
    height: int
    data: bytes

    @property
    def mime_type(self) -> str:
        return MIME[self.format]


@dataclass
class ProcessedImage:
    source_mime: str
    width: int
    height: int
    has_alpha: bool
    is_graphic: bool
    dominant_color: str
    files: list[EncodedFile] = field(default_factory=list)
    master: bytes | None = None


# ---- validation -------------------------------------------------------------------


def _looks_like_markup(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith((b"<", b"\xef\xbb\xbf<")) or b"<svg" in head


def open_validated(data: bytes, *, max_bytes: int, max_pixels: int, max_dimension: int):
    """Return (image, source_mime) or raise ImageRejected."""
    if not data:
        raise ImageRejected("The file is empty.")
    if len(data) > max_bytes:
        raise ImageRejected(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    if _looks_like_markup(data):
        raise ImageRejected(
            "SVG and other markup files are not accepted. Upload a PNG, JPEG, WebP or AVIF."
        )
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                probe = Image.open(io.BytesIO(data))
            except (Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ImageRejected("The image has too many pixels.") from None
            except Exception:
                raise ImageRejected(
                    "This file is not a supported image. Upload a PNG, JPEG, WebP or AVIF."
                ) from None
            fmt = probe.format
            if fmt not in SUPPORTED_FORMATS:
                raise ImageRejected(f"{fmt or 'This'} images are not supported.")
            width, height = probe.size
            if width < 1 or height < 1:
                raise ImageRejected("The image has no pixels.")
            if max(width, height) > max_dimension:
                raise ImageRejected(f"Images can be at most {max_dimension}px on each side.")
            if width * height > max_pixels:
                raise ImageRejected("The image has too many pixels.")
            if getattr(probe, "n_frames", 1) > 1:
                raise ImageRejected("Animated images are not supported.")
            try:
                probe.verify()  # structural check (truncation, corrupt chunks)
                image = Image.open(io.BytesIO(data))
                image.load()
            except (Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ImageRejected("The image has too many pixels.") from None
            except Exception:
                raise ImageRejected("The image file is damaged or incomplete.") from None
    finally:
        Image.MAX_IMAGE_PIXELS = previous
    return image, SUPPORTED_FORMATS[fmt]


def normalise(image: Image.Image) -> tuple[Image.Image, bool]:
    """Apply orientation, convert to sRGB RGB/RGBA. Returns (image, has_alpha)."""
    image = ImageOps.exif_transpose(image)
    icc = image.info.get("icc_profile")
    if image.mode == "CMYK" and not icc:
        image = image.convert("RGB")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            mode = "RGBA" if "A" in image.getbands() else "RGB"
            if image.mode not in ("RGB", "RGBA", "CMYK", "L"):
                image = image.convert("RGBA" if mode == "RGBA" else "RGB")
            image = ImageCms.profileToProfile(image, src, dst, outputMode=mode)
        except Exception:  # unreadable profile: fall back to a plain conversion
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    if image.mode in ("P", "LA", "La", "PA") or (
        image.mode in ("L", "RGB") and "transparency" in image.info
    ):
        image = image.convert("RGBA")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    has_alpha = image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255
    if image.mode == "RGBA" and not has_alpha:
        image = image.convert("RGB")
    image.info.clear()  # never carry EXIF/XMP/ICC into derivatives
    return image, has_alpha


def is_graphic(image: Image.Image) -> bool:
    """Heuristic: flat-colour artwork, text and screenshots compress better losslessly."""
    sample = image.convert("RGB")
    sample.thumbnail((256, 256))
    colors = sample.getcolors(maxcolors=4096)
    return colors is not None and len(colors) <= 1024


def dominant_color(image: Image.Image) -> str:
    rgb = image.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ---- geometry -----------------------------------------------------------------------


def crop_to_aspect(image: Image.Image, aspect: float, focal: tuple[float, float]) -> Image.Image:
    width, height = image.size
    if abs(width / height - aspect) < 0.01:
        return image
    if width / height > aspect:
        new_w, new_h = round(height * aspect), height
    else:
        new_w, new_h = width, round(width / aspect)
    fx, fy = focal
    left = min(max(round(fx * width - new_w / 2), 0), width - new_w)
    top = min(max(round(fy * height - new_h / 2), 0), height - new_h)
    return image.crop((left, top, left + new_w, top + new_h))


def resize_to_width(image: Image.Image, width: int) -> Image.Image:
    if width >= image.width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def target_widths(preset: Preset, source_width: int) -> list[int]:
    """Widths for this preset without upscaling (a small original gets one variant)."""
    limit = min(source_width, preset.max_width)
    allowed = [w for w in preset.widths if w <= limit]
    # Keep the full available resolution when it falls between standard widths
    # (e.g. a 741px original gets 160/320/640/741), unless it is barely larger.
    if not allowed or (limit not in allowed and limit > allowed[-1] * 1.15):
        allowed.append(limit)
    return allowed


# ---- encoding -----------------------------------------------------------------------


def _flatten(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image.convert("RGB")
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.getchannel("A"))
    return background


def psnr(reference: Image.Image, encoded: bytes) -> float:
    """Peak signal-to-noise ratio of an encoding against its source (higher = closer)."""
    with Image.open(io.BytesIO(encoded)) as decoded:
        a, b = _flatten(reference), _flatten(decoded.convert(reference.mode))
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    mse = sum(stat.sum2) / (a.width * a.height * 3)
    return 99.0 if mse == 0 else 10 * math.log10(255**2 / mse)


def encode(image: Image.Image, fmt: str, *, quality: int = 80, lossless: bool = False) -> bytes:
    buf = io.BytesIO()
    if fmt == "webp":
        image.save(buf, "WEBP", quality=quality, method=5, lossless=lossless)
    elif fmt == "avif":
        image.save(buf, "AVIF", quality=quality, speed=6)
    elif fmt == "jpeg":
        _flatten(image).save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    elif fmt == "png":
        image.save(buf, "PNG", optimize=True)
    else:  # pragma: no cover
        raise ValueError(fmt)
    return buf.getvalue()


MIN_PHOTO_QUALITY = 64
MIN_PSNR = 34.0  # below this, artefacts become noticeable on photographs


def encode_webp(image: Image.Image, preset: Preset, graphic: bool) -> bytes:
    if graphic:
        # Sharp edges and text: compare lossless with high-quality lossy and keep the
        # smaller one unless the lossy version visibly degrades the artwork.
        lossless = encode(image, "webp", lossless=True)
        lossy = encode(image, "webp", quality=90)
        if len(lossy) < len(lossless) and psnr(image, lossy) >= 40:
            return lossy
        return lossless
    quality = preset.quality
    best = encode(image, "webp", quality=quality)
    # Only the typical display width is held to the target; larger files are expected
    # for 1600px sources. Step quality down while it stays visually clean.
    target = preset.target_kb[1] * 1024 * max(1.0, (image.width / 960) ** 2)
    while len(best) > target and quality - 6 >= MIN_PHOTO_QUALITY:
        candidate = encode(image, "webp", quality=quality - 6)
        if psnr(image, candidate) < MIN_PSNR:
            break
        quality -= 6
        best = candidate
    return best


def maybe_avif(image: Image.Image, webp: bytes, graphic: bool) -> bytes | None:
    """AVIF only when clearly smaller and not meaningfully worse than the WebP."""
    if "AVIF" not in SUPPORTED_FORMATS:
        return None
    avif = encode(image, "avif", quality=72 if graphic else 58)
    if len(avif) >= len(webp) * 0.92:
        return None
    if psnr(image, avif) < psnr(image, webp) - 1.5:
        return None
    return avif


def build_preset(
    image: Image.Image,
    preset: Preset,
    *,
    has_alpha: bool,
    graphic: bool,
    focal: tuple[float, float],
    avif: bool,
) -> list[EncodedFile]:
    base = crop_to_aspect(image, preset.aspect, focal) if preset.aspect else image
    files: list[EncodedFile] = []
    widths = target_widths(preset, base.width)
    fallback_fmt = "png" if has_alpha or (graphic and preset.name != "social") else "jpeg"
    if preset.name == "social":
        # Social networks are most reliable with a single JPEG of the exact size.
        resized = resize_to_width(base, widths[-1])
        data = encode(resized, "jpeg", quality=preset.quality)
        return [EncodedFile(preset.name, "jpeg", resized.width, resized.height, data)]
    for width in widths:
        resized = resize_to_width(base, width)
        webp = encode_webp(resized, preset, graphic)
        files.append(EncodedFile(preset.name, "webp", resized.width, resized.height, webp))
        if avif and (data := maybe_avif(resized, webp, graphic)):
            files.append(EncodedFile(preset.name, "avif", resized.width, resized.height, data))
    # Fallbacks for browsers without WebP support: a mid and a large size.
    fallback_widths = sorted({widths[0] if len(widths) < 3 else widths[2], widths[-1]})
    if len(widths) >= 5:
        fallback_widths = [w for w in (640, 1280) if w in widths] or fallback_widths
    for width in fallback_widths:
        resized = resize_to_width(base, width)
        quality = 82
        data = encode(resized, fallback_fmt, quality=quality)
        files.append(EncodedFile(preset.name, fallback_fmt, resized.width, resized.height, data))
    return files


def process(
    data: bytes,
    *,
    max_bytes: int,
    max_pixels: int,
    max_dimension: int,
    focal: tuple[float, float] = (0.5, 0.5),
    presets: tuple[str, ...] | None = None,
    avif: bool = True,
    keep_master: bool = False,
) -> ProcessedImage:
    image, source_mime = open_validated(
        data, max_bytes=max_bytes, max_pixels=max_pixels, max_dimension=max_dimension
    )
    image, has_alpha = normalise(image)
    graphic = is_graphic(image)
    result = ProcessedImage(
        source_mime=source_mime,
        width=image.width,
        height=image.height,
        has_alpha=has_alpha,
        is_graphic=graphic,
        dominant_color=dominant_color(image),
    )
    names = presets or tuple(p.name for p in PRESETS.values() if p.on_upload)
    for name in names:
        preset = PRESETS[name]
        if preset.mode != "cropped":
            continue
        result.files.extend(
            build_preset(
                image, preset, has_alpha=has_alpha, graphic=graphic, focal=focal, avif=avif
            )
        )
    if keep_master:
        master = image.copy()
        master.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        result.master = (
            encode(master, "png") if graphic or has_alpha else encode(master, "webp", quality=92)
        )
    return result


def slugify(value: str, fallback: str = "image") -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    value = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", value.strip())
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:60].strip("-") or fallback
