"""RQ worker entry point — run as `python -m app.scraper.worker`.

Listens on the `scraper` queue and executes scrape jobs enqueued by the web
process. Requires REDIS_URL in the environment.
"""
from __future__ import annotations

import logging
import os
import sys


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stdout,
    )
    log = logging.getLogger('scraper-worker')

    url = (os.environ.get('REDIS_URL') or '').strip()
    if not url:
        log.error('REDIS_URL is not set — refusing to start worker. '
                  'Set REDIS_URL or rely on the in-process thread fallback.')
        return 2

    try:
        import redis
        from rq import Worker, Queue
    except ImportError:
        log.error('rq/redis not installed — add them to requirements.txt')
        return 2

    conn = redis.from_url(url)
    conn.ping()
    queue = Queue('scraper', connection=conn)
    log.info(f'[worker] connected to {url}, listening on "scraper"')
    Worker([queue], connection=conn).work(with_scheduler=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
