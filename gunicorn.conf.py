"""Gunicorn config for production (Railway) and local runs.

Tuning philosophy:
  * Requests should be < 10s. The scraper is a background job — web workers
    never wait on it. 120s timeout is a safety net for slow DB queries, not a
    feature.
  * Thread workers (`gthread`) are the right choice for this I/O-heavy workload:
    Postgres, R2, SMS, OpenAI — all waiting on network. Async workers would
    require swapping SQLAlchemy for async drivers.
  * Workers * threads = concurrency ceiling. On a Railway "Hobby" plan (1 CPU,
    512MB RAM) we keep workers modest to avoid OOM.
"""
from __future__ import annotations

import multiprocessing
import os


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


# Binding
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# Worker model
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'gthread')
workers      = _int('WEB_CONCURRENCY', max(2, multiprocessing.cpu_count()))
threads      = _int('GUNICORN_THREADS', 4)

# Timeouts
timeout         = _int('GUNICORN_TIMEOUT', 120)
graceful_timeout = _int('GUNICORN_GRACEFUL_TIMEOUT', 30)
keepalive       = _int('GUNICORN_KEEPALIVE', 5)

# Request handling
max_requests        = _int('GUNICORN_MAX_REQUESTS', 1000)
max_requests_jitter = _int('GUNICORN_MAX_REQUESTS_JITTER', 100)

# Proxy awareness — Railway puts requests behind its edge
forwarded_allow_ips = '*'
proxy_allow_ips     = '*'
proxy_protocol      = False

# Logging
accesslog  = '-'
errorlog   = '-'
loglevel   = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(L)ss'
)

# Startup hygiene
preload_app = os.environ.get('GUNICORN_PRELOAD', '0') == '1'
