"""Strict child profile-photo normalization.

Only decoded pixels survive this boundary. Original containers, EXIF metadata,
animation, and trailing payloads are discarded before bytes reach PostgreSQL.
"""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings

READ_CHUNK_BYTES = 64 * 1024
SUPPORTED_INPUT_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True)
class NormalizedProfilePhoto:
    image_bytes: bytes
    content_type: str
    width: int
    height: int
    sha256: str
    original_filename: str | None

    @property
    def size_bytes(self) -> int:
        return len(self.image_bytes)


def _safe_filename(value: str | None) -> str | None:
    if not value:
        return None
    # Browsers normally send only a basename, but treat both path separators as
    # untrusted and never reflect control characters into Content-Disposition.
    cleaned = value.replace("\\", "/").split("/")[-1]
    cleaned = "".join(character for character in cleaned if ord(character) >= 32).strip()
    return cleaned[:255] or None


def _read_limited(upload: UploadFile, maximum: int) -> bytes:
    result = bytearray()
    while True:
        chunk = upload.file.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        result.extend(chunk)
        if len(result) > maximum:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Profile photo must be {maximum // (1024 * 1024)} MB or smaller",
            )
    if not result:
        raise HTTPException(status_code=422, detail="Profile photo is empty")
    return bytes(result)


def _has_transparency(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)


def normalize_profile_photo(upload: UploadFile, settings: Settings) -> NormalizedProfilePhoto:
    """Decode, bound, orient, resize, and re-encode an uploaded profile image."""

    raw = _read_limited(upload, settings.child_profile_photo_max_bytes)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as probe:
                if (probe.format or "").upper() not in SUPPORTED_INPUT_FORMATS:
                    raise HTTPException(
                        status_code=422,
                        detail="Profile photo must be a JPEG, PNG, or WebP image",
                    )
                width, height = probe.size
                if width <= 0 or height <= 0:
                    raise HTTPException(status_code=422, detail="Profile photo has no pixels")
                if width * height > settings.child_profile_photo_max_pixels:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Profile photo pixel dimensions are too large",
                    )
                if getattr(probe, "n_frames", 1) != 1:
                    raise HTTPException(
                        status_code=422,
                        detail="Animated profile photos are not supported",
                    )
                probe.verify()

            with Image.open(BytesIO(raw)) as decoded:
                oriented = ImageOps.exif_transpose(decoded)
                oriented.thumbnail(
                    (
                        settings.child_profile_photo_max_edge,
                        settings.child_profile_photo_max_edge,
                    ),
                    Image.Resampling.LANCZOS,
                )
                transparent = _has_transparency(oriented)
                normalized = oriented.convert("RGBA" if transparent else "RGB")
                output = BytesIO()
                if transparent:
                    normalized.save(output, format="WEBP", quality=90, method=6)
                    content_type = "image/webp"
                else:
                    normalized.save(
                        output,
                        format="JPEG",
                        quality=88,
                        optimize=True,
                        progressive=True,
                    )
                    content_type = "image/jpeg"
                output_bytes = output.getvalue()
                width, height = normalized.size
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Profile photo pixel dimensions are too large",
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="Profile photo is not a valid JPEG, PNG, or WebP image",
        ) from None

    if not output_bytes or len(output_bytes) > settings.child_profile_photo_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Normalized profile photo is too large",
        )
    return NormalizedProfilePhoto(
        image_bytes=output_bytes,
        content_type=content_type,
        width=width,
        height=height,
        sha256=hashlib.sha256(output_bytes).hexdigest(),
        original_filename=_safe_filename(upload.filename),
    )
