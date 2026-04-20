"""Cloudflare R2 (S3-compatible) photo storage service."""
import os
import uuid
import logging

import requests as _req

logger = logging.getLogger(__name__)

R2_ENDPOINT = os.environ.get('R2_ENDPOINT', '').strip()
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID', '').strip()
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '').strip()
R2_BUCKET = os.environ.get('R2_BUCKET', '').strip()
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL', '').strip()


def _get_client():
    if not all([R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET]):
        return None
    try:
        import boto3
        return boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto',
        )
    except ImportError:
        logger.warning('[R2] boto3 not installed — photo upload disabled')
        return None


def _upload_bytes(data: bytes, key: str, content_type: str = 'image/jpeg') -> str | None:
    client = _get_client()
    if not client:
        return None
    try:
        client.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType=content_type)
        base = R2_PUBLIC_URL.rstrip('/')
        return f'{base}/{key}' if base else None
    except Exception as e:
        logger.warning(f'[R2] Upload failed for {key}: {e}')
        return None


def upload_from_url(url: str, prefix: str = 'photos') -> str | None:
    """Download URL and upload to R2. Returns public URL or None."""
    try:
        r = _req.get(url, timeout=15)
        if r.status_code != 200 or len(r.content) < 5000:
            return None
        key = f'{prefix}/{uuid.uuid4().hex}.jpg'
        return _upload_bytes(r.content, key)
    except Exception as e:
        logger.warning(f'[R2] upload_from_url error: {e}')
        return None


def upload_from_path(path: str, prefix: str = 'photos') -> str | None:
    """Upload local file to R2. Returns public URL or None."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
        if len(data) < 5000:
            return None
        ext = os.path.splitext(path)[1].lstrip('.') or 'jpg'
        key = f'{prefix}/{uuid.uuid4().hex}.{ext}'
        return _upload_bytes(data, key)
    except Exception as e:
        logger.warning(f'[R2] upload_from_path error: {e}')
        return None
