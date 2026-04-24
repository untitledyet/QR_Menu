# -*- coding: utf-8 -*-
# Entry point for gunicorn: `gunicorn manage:app --config gunicorn.conf.py`
# DB migrations are managed by Flask-Migrate (Alembic): `flask db upgrade`
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()
