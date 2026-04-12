import os
from flask import Flask
from .config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

db = SQLAlchemy()
migrate = Migrate()

load_dotenv()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    print(f"SQLALCHEMY_DATABASE_URI კონფიგიდან: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    print(f"DATABASE_URL გარემოს ცვლადებიდან: {os.environ.get('DATABASE_URL')}")

    db.init_app(app)
    migrate.init_app(app, db)

    # ლოგირება — utils/logging.py-ს გამოყენება
    from app.utils.logging import setup_logging
    setup_logging(app)

    # Blueprint-ების რეგისტრაცია
    from app.routes.menu_routes import menu_bp
    from app.routes.api_routes import api_bp
    from app.routes.backoffice_routes import bo_bp
    from app.routes.reservation_api_routes import res_api_bp
    from app.routes.landing_routes import landing_bp
    app.register_blueprint(landing_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(bo_bp)
    app.register_blueprint(res_api_bp)

    # Feature Flags
    from app.utils.feature_flags import init_feature_flags
    init_feature_flags(app)

    return app
