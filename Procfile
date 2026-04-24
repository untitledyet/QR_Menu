web: gunicorn manage:app --config gunicorn.conf.py
worker: python -m app.scraper.worker
release: flask db upgrade
