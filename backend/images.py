from __future__ import annotations

import hashlib
import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 15 * 1024 * 1024
MAX_SIDE = 4096
Image.MAX_IMAGE_PIXELS = 8192 * 4096


def decode(data: bytes, panorama=False):
    if len(data) > MAX_BYTES:
        raise ValueError("Photo exceeds the 15 MB limit.")
    if not data:
        raise ValueError("Choose a JPEG, PNG, or WebP photo.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Only JPEG, PNG, and WebP photos are supported.")
                ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[source.format]
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not supported. Choose a still photo.")
                limit = 8192 if panorama else MAX_SIDE
                if max(source.size) > limit or min(source.size) < 32:
                    raise ValueError(f"Each image dimension must be between 32 and {limit} pixels.")
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGBA")
                background = Image.new("RGBA", oriented.size, "#ffffff")
                image = Image.alpha_composite(background, oriented).convert("RGB")
                if panorama and image.width != image.height * 2:
                    raise ValueError("A 360° panorama must be a full equirectangular image with a 2:1 width-to-height ratio. Use AI generation for an ordinary photo.")
        return image, ext, hashlib.sha256(data).hexdigest()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("This photo could not be decoded safely. Try a different file.") from exc
