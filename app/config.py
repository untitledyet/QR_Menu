import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_secret_key_here'
    DEBUG = os.environ.get('FLASK_DEBUG') or True

    # SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+mysqlconnector://root:Test1234%40@localhost:3306/testing'
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Feature Flags settings
    FEATURE_FLAGS = {
        'enable_login': True,
        'enable_new_dishes': True,
        'enable_promotions': True,
        'enable_cart_functionality': True,  # False by default, to be enabled for premium users
    }

    # Logging settings
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')

    # Other configurations
    ITEMS_PER_PAGE = 10
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # Security settings
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
