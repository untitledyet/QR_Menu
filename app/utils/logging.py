"""Logging configuration.

Two modes:
  * Dev (LOG_JSON unset): plain human-readable formatter on stdout+rotating file.
  * Prod (LOG_JSON=1):    structlog-based JSON output — query-friendly in
    BetterStack/Logtail/Datadog/CloudWatch. Falls back to plain text if
    structlog is not installed (e.g. CI env without all deps).

Structured helper: `get_logger(__name__)` returns a structlog logger in JSON
mode, or the stdlib logger otherwise. Both accept keyword arguments:

    log = get_logger("scraper")
    log.info("job_started", venue_id=42, place_id=pid)
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _json_enabled(app) -> bool:
    return str(app.config.get('LOG_JSON') or os.environ.get('LOG_JSON', '0')).lower() in ('1', 'true', 'yes')


def _install_structlog(level: int):
    """Configure structlog for JSON output to stdout."""
    try:
        import structlog
    except ImportError:
        return False

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt='iso', utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through structlog too so `logger.info("msg")` emits JSON.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    return True


def setup_logging(app):
    """Configure Flask app logging. Idempotent — safe to call repeatedly."""
    level = logging.DEBUG if app.debug else logging.INFO
    app.logger.setLevel(level)

    if _json_enabled(app):
        if _install_structlog(level):
            app.logger.info('MenuApp startup (JSON logging)')
            return
        # Fallthrough to plain logging if structlog is missing

    # Plain logging — file + optional stdout
    if not os.path.exists('logs'):
        try:
            os.mkdir('logs')
        except OSError:
            pass

    # Clear existing handlers to stay idempotent on reload
    app.logger.handlers[:] = []
    root = logging.getLogger()
    root.handlers[:] = []
    root.setLevel(level)

    fmt = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s]: %(message)s'
    )

    try:
        file_handler = RotatingFileHandler('logs/menu_app.log', maxBytes=10 * 1024 * 1024, backupCount=10)
        file_handler.setFormatter(fmt)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
        app.logger.propagate = True
    except Exception:
        pass  # Read-only filesystem (some deploy envs)

    if app.config.get('LOG_TO_STDOUT'):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        stream_handler.setLevel(level)
        root.addHandler(stream_handler)

    app.logger.info('MenuApp startup')


def get_logger(name: str):
    """Return a structlog logger if structlog is configured, else stdlib."""
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)
