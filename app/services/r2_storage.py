"""Cloudflare R2 (S3-compatible) photo storage.

Key properties of this implementation:
  * Content-addressable keys (SHA-256 prefix) → automatic deduplication across
    scraper runs, saves Class A writes on R2.
  * On-the-fly compression: max 1600px, WebP q=85 (falls back to JPEG).
  * HEAD check before every PUT: if the object already exists, we skip the write
    and return the existing public URL.
  * `no_compress=True` passthrough for things like debug screenshots where we
    want the full raw payload.
"""
from __future__ import annotations

import hashlib
import logging
import os
from functools import lru_cache
from typing import Optional

import requests as _req

logger = logging.getLogger(__name__)


def _clean(val: str) -> str:
    """Strip any whitespace (incl. embedded newlines) copied-in from Railway."""
    return ''.join((val or '').split())


R2_ENDPOINT          = _clean(os.environ.get('R2_ENDPOINT', ''))
R2_ACCESS_KEY_ID     = _clean(os.environ.get('R2_ACCESS_KEY_ID', ''))
R2_SECRET_ACCESS_KEY = _clean(os.environ.get('R2_SECRET_ACCESS_KEY', ''))
R2_BUCKET            = _clean(os.environ.get('R2_BUCKET', ''))
R2_PUBLIC_URL        = _clean(os.environ.get('R2_PUBLIC_URL', ''))

# Minimum accepted size — tiny images are usually tracking pixels or HTTP errors
MIN_BYTES = 5000


@lru_cache(maxsize=1)
def _get_client():
    if not all([R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET]):
        return None
    try:
        import boto3
        from botocore.config import Config as BotoConfig
        return boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto',
            config=BotoConfig(
                retries={'max_attempts': 3, 'mode': 'standard'},
                connect_timeout=5,
                read_timeout=30,
            ),
        )
    except ImportError:
        logger.warning('[R2] boto3 not installed — photo upload disabled')
        return None


def _public_url(key: str) -> Optional[str]:
    base = R2_PUBLIC_URL.rstrip('/')
    return f'{base}/{key}' if base else None


def _object_exists(client, key: str) -> bool:
    try:
        client.head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except Exception:
        return False


def _content_addressable_key(prefix: str, data: bytes, ext: str) -> str:
    """Derive a content-addressable key so identical bytes → identical key."""
    digest = hashlib.sha256(data).hexdigest()[:24]
    prefix = prefix.strip('/').strip() or 'photos'
    return f'{prefix}/{digest}.{ext.lstrip(".")}'


def _compress(data: bytes, max_px: int, quality: int) -> tuple[bytes, str]:
    """Return (bytes, extension) after compression. No-op on failure."""
    try:
        from app.scraper.image_preprocessor import prepare_bytes_for_storage
        return prepare_bytes_for_storage(data, max_px=max_px, quality=quality)
    except Exception as e:
        logger.warning(f'[R2] compression failed, storing raw: {e}')
        return data, 'jpg'


def _upload_bytes(
    data: bytes,
    *,
    prefix: str,
    no_compress: bool = False,
    max_px: int = 1600,
    quality: int = 85,
    content_type: Optional[str] = None,
) -> Optional[str]:
    client = _get_client()
    if not client or len(data) < MIN_BYTES:
        return None

    if no_compress:
        payload, ext = data, 'jpg'
        ctype = content_type or 'image/jpeg'
    else:
        payload, ext = _compress(data, max_px=max_px, quality=quality)
        ctype = content_type or ('image/webp' if ext == 'webp' else 'image/jpeg')

    key = _content_addressable_key(prefix, payload, ext)
    url = _public_url(key)

    if _object_exists(client, key):
        return url

    try:
        client.put_object(
            Bucket=R2_BUCKET, Key=key, Body=payload, ContentType=ctype,
            CacheControl='public, max-age=31536000, immutable',
        )
        return url
    except Exception as e:
        logger.warning(f'[R2] Upload failed for {key}: {e}')
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def upload_from_url(url: str, prefix: str = 'photos', **kwargs) -> Optional[str]:
    """Download URL and upload to R2. Returns public URL or None."""
    try:
        r = _req.get(url, timeout=15)
        if r.status_code != 200:
            return None
        return _upload_bytes(r.content, prefix=prefix, **kwargs)
    except Exception as e:
        logger.warning(f'[R2] upload_from_url error: {e}')
        return None


def upload_from_path(path: str, prefix: str = 'photos', **kwargs) -> Optional[str]:
    """Upload local file to R2. Returns public URL or None."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
        return _upload_bytes(data, prefix=prefix, **kwargs)
    except Exception as e:
        logger.warning(f'[R2] upload_from_path error: {e}')
        return None


def upload_bytes(data: bytes, prefix: str = 'photos', **kwargs) -> Optional[str]:
    """Upload raw bytes to R2 (primary entry point when you already hold bytes)."""
    return _upload_bytes(data, prefix=prefix, **kwargs)
