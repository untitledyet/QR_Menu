"""Error monitoring + rate-limiter wiring.

Both integrations are optional — if the required env var is absent or the SDK
is not installed we no-op so local dev / CI stay frictionless.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# ── Sentry ────────────────────────────────────────────────────────────────────

def init_sentry(app) -> None:
    dsn = os.environ.get('SENTRY_DSN', '').strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        env = os.environ.get('SENTRY_ENV') or ('production' if not app.debug else 'development')
        release = os.environ.get('SENTRY_RELEASE') or os.environ.get('RAILWAY_GIT_COMMIT_SHA')

        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            release=release,
            integrations=[
                FlaskIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            profiles_sample_rate=float(os.environ.get('SENTRY_PROFILES_SAMPLE_RATE', '0.0')),
            send_default_pii=False,
            attach_stacktrace=True,
        )
        app.logger.info(f'[Sentry] initialized env={env}')
    except ImportError:
        app.logger.warning('[Sentry] sentry-sdk not installed — skipping')
    except Exception as e:
        app.logger.warning(f'[Sentry] init failed: {e}')


# ── Rate limiter ──────────────────────────────────────────────────────────────

_limiter = None


def get_limiter():
    """Return the lazily-initialized Flask-Limiter instance (or None)."""
    return _limiter


def init_rate_limiter(app):
    """Attach Flask-Limiter to the app. Uses Redis when REDIS_URL is set,
    falls back to in-memory otherwise (fine for single-worker dev)."""
    global _limiter
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
    except ImportError:
        app.logger.warning('[Limiter] flask-limiter not installed — skipping')
        return None

    storage_uri = os.environ.get('RATELIMIT_STORAGE_URI') or os.environ.get('REDIS_URL') or 'memory://'

    _limiter = Limiter(
        get_remote_address,
        app=app,
        storage_uri=storage_uri,
        default_limits=[],  # per-route limits only — no blanket default
        headers_enabled=True,
    )
    app.logger.info(f'[Limiter] initialized storage={storage_uri.split("://")[0]}')
    return _limiter


def rate_limit(*limits: str):
    """Decorator that applies Flask-Limiter limits when available, no-op otherwise.

    Usage:
        @landing_bp.route(...)
        @rate_limit('10/hour', '3/minute')
        def login(): ...

    Safe to use at import time — route modules may be imported before the limiter
    is attached to the app. The wrapped function caches the composed limited
    version on first call.
    """
    def decorator(fn):
        from functools import wraps

        state = {'limited': None}

        @wraps(fn)
        def wrapper(*args, **kwargs):
            if state['limited'] is not None:
                return state['limited'](*args, **kwargs)
            lim = _limiter
            if lim is None:
                return fn(*args, **kwargs)
            limited = fn
            for expr in limits:
                limited = lim.limit(expr)(limited)
            state['limited'] = limited
            return limited(*args, **kwargs)

        return wrapper

    return decorator
