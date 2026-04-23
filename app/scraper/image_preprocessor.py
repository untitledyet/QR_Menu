"""Image preprocessing for OCR/vision calls.

Pipeline:
  1. Honor EXIF orientation (many phone uploads are rotated)
  2. Convert to RGB (avoid palette/RGBA surprises in JPEG)
  3. Auto-contrast + mild sharpen (dark/faded menu photos)
  4. Downscale to VISION_MAX_PX on longest side
  5. Re-encode JPEG q=92 (balance fidelity vs payload size)

Returns bytes + mime. Never raises — on any failure returns the raw file bytes.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Tuple

from . import config

logger = logging.getLogger(__name__)

_MIME_MAP = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "webp": "image/webp", "gif": "image/gif",
}


def _mime_for(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _MIME_MAP.get(ext, "image/jpeg")


def prepare_for_vision(path: str) -> Tuple[bytes, str]:
    """Load, normalize, and downscale an image for vision API upload.

    Returns (bytes, mime_type). Falls back to raw file bytes on any error.
    """
    try:
        from PIL import Image, ImageOps, ImageFilter
    except ImportError:
        logger.warning("[preprocess] Pillow not installed — sending raw bytes")
        with open(path, "rb") as f:
            return f.read(), _mime_for(path)

    try:
        with Image.open(path) as im:
            # EXIF orientation (smartphone uploads)
            im = ImageOps.exif_transpose(im)

            # Normalize colour mode
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")

            # Auto-contrast handles dark/faded menu photos
            try:
                im = ImageOps.autocontrast(im, cutoff=1)
            except Exception:
                pass

            # Gentle unsharp to help OCR on small text
            try:
                im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))
            except Exception:
                pass

            # Downscale if oversized
            max_px = config.VISION_MAX_PX
            if max(im.size) > max_px:
                im.thumbnail((max_px, max_px), Image.LANCZOS)

            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=92, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception as e:
        logger.warning(f"[preprocess] {os.path.basename(path)}: {e} — using raw")
        try:
            with open(path, "rb") as f:
                return f.read(), _mime_for(path)
        except Exception:
            return b"", _mime_for(path)


def prepare_bytes_for_storage(data: bytes, max_px: int = 1600, quality: int = 85) -> Tuple[bytes, str]:
    """Compress bytes for R2 storage (WebP when available, JPEG fallback).

    Returns (bytes, extension) where extension is 'webp' or 'jpg'.
    Falls back to original bytes + 'jpg' if PIL unavailable.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, "jpg"

    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            if max(im.size) > max_px:
                im.thumbnail((max_px, max_px), Image.LANCZOS)

            buf = io.BytesIO()
            try:
                # WebP is smaller at equivalent quality
                save_im = im.convert("RGB") if im.mode == "RGBA" else im
                save_im.save(buf, format="WEBP", quality=quality, method=6)
                return buf.getvalue(), "webp"
            except Exception:
                buf = io.BytesIO()
                im.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
                return buf.getvalue(), "jpg"
    except Exception as e:
        logger.warning(f"[preprocess] storage compress failed: {e}")
        return data, "jpg"
