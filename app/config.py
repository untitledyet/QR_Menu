import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

    # Railway provides DATABASE_URL; fallback to SQLite for local dev
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///menu.db')
    # Railway Postgres URLs start with postgres:// but SQLAlchemy needs postgresql://
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT', '1')

    FEATURE_FLAGS = {
        'enable_login': True,
        'enable_new_dishes': True,
        'enable_promotions': True,
        'enable_cart_functionality': True,
    }

    SESSION_COOKIE_SECURE = os.environ.get('FLASK_DEBUG', '0') != '1'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_DEBUG', '0') != '1'

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
