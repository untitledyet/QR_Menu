web: gunicorn manage:app --config gunicorn.conf.py
worker: python -m app.scraper.worker
release: echo "migrations run at container start via startCommand"
