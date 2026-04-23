web: gunicorn manage:app --config gunicorn.conf.py
worker: python -m app.scraper.worker
release: python -c "from manage import run_migrations; run_migrations()"
