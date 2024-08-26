import os
from flask import Flask
from .config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# მონაცემთა ბაზის ობიექტის შექმნა, რომელიც მოგვიანებით იქნება ინიციალიზებული აპლიკაციასთან
db = SQLAlchemy()
migrate = Migrate()

# გარემოს ცვლადების დატვირთვა
load_dotenv()


def create_app(config_class=Config):
    # Flask აპლიკაციის შექმნა და კონფიგურაციის ჩატვირთვა
    app = Flask(__name__)
    app.config.from_object(config_class)

    print(f"SQLALCHEMY_DATABASE_URI კონფიგიდან: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    print(f"DATABASE_URL გარემოს ცვლადებიდან: {os.environ.get('DATABASE_URL')}")

    # მონაცემთა ბაზისა და მიგრაციის ინიციალიზაცია
    db.init_app(app)
    migrate.init_app(app, db)

    # ლოგირების დაყენება
    if not os.path.exists('logs'):
        os.mkdir('logs')

    file_handler = RotatingFileHandler('logs/menu_app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    if app.config.get("LOG_TO_STDOUT"):  # თუ ლოგირების stdout-ში ჩართვა ჩართულია (მაგ. Docker-ში)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        app.logger.addHandler(stream_handler)
    else:
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('MenuApp startup')

    # Blueprint-ების რეგისტრაცია
    from app.routes.menu_routes import menu_bp
    from app.routes.api_routes import api_bp

    app.register_blueprint(menu_bp)
    app.register_blueprint(api_bp)

    # Feature Flags-ის ინიციალიზაცია
    from app.utils.feature_flags import init_feature_flags
    init_feature_flags(app)

    return app
