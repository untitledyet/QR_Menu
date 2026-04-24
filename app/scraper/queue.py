"""Task queue abstraction for the scraper pipeline.

Two execution modes, chosen at runtime:

  * Redis present (REDIS_URL)        → enqueue on RQ, worker process picks it up.
  * Otherwise (local dev, no Redis)  → spawn a background thread in-process.

The scraper pipeline itself is identical in both modes — the worker just calls
`run_scraper_job(venue_id, place_id, venue_name)` which reconstructs the Flask
app context internally.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_QUEUE_NAME = 'scraper'


def _redis_url() -> Optional[str]:
    url = (os.environ.get('REDIS_URL') or '').strip()
    return url or None


def _get_queue():
    """Return an RQ Queue bound to Redis, or None if unavailable."""
    url = _redis_url()
    if not url:
        return None
    try:
        import redis
        from rq import Queue
        conn = redis.from_url(url)
        conn.ping()  # fail fast if Redis is unreachable
        return Queue(_QUEUE_NAME, connection=conn, default_timeout=900)
    except Exception as e:
        logger.warning(f'[Queue] Redis unavailable — falling back to thread: {e}')
        return None


def enqueue_scraper_job(app, venue_id: int, place_id: str, venue_name: str) -> str:
    """Queue a scrape. Returns a tracking handle (RQ job id or thread name)."""
    if not place_id:
        return ''

    q = _get_queue()
    if q is not None:
        # NB: we pass only plain args — the worker rebuilds app context itself.
        job = q.enqueue(
            'app.scraper.queue.run_scraper_job',
            venue_id, place_id, venue_name,
            job_timeout=900,
            result_ttl=86400,
            failure_ttl=86400 * 7,
            description=f'scrape venue={venue_id}',
        )
        logger.info(f'[Queue] enqueued venue_id={venue_id} job={job.id}')
        return job.id

    t = threading.Thread(
        target=_run_in_thread,
        args=(app, venue_id, place_id, venue_name),
        daemon=True,
        name=f'scraper-{venue_id}',
    )
    t.start()
    logger.info(f'[Queue] thread fallback venue_id={venue_id} thread={t.name}')
    return t.name


def _run_in_thread(app, venue_id: int, place_id: str, venue_name: str):
    """Thread-mode entry — pipeline expects a Flask app context."""
    from app.scraper.job_runner import _worker
    _worker(app, venue_id, place_id, venue_name)


def run_scraper_job(venue_id: int, place_id: str, venue_name: str):
    """RQ entry point — runs in the worker process, rebuilds its own app context."""
    from app import create_app
    from app.scraper.job_runner import _worker
    app = create_app()
    _worker(app, venue_id, place_id, venue_name)
