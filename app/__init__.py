# -*- coding: utf-8 -*-
from flask import Flask, jsonify, send_from_directory
from sqlalchemy import text
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

    # Sentry must initialise before anything else so early errors are captured.
    from app.utils.observability import init_sentry, init_rate_limiter
    init_sentry(app)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.utils.logging import setup_logging
    setup_logging(app)

    # Rate limiter (no-op if flask-limiter is absent)
    init_rate_limiter(app)

    from app.routes.menu_routes import menu_bp
    from app.routes.api_routes import api_bp
    from app.routes.backoffice_routes import bo_bp
    from app.routes.reservation_api_routes import res_api_bp
    from app.routes.landing_routes import landing_bp
    from app.routes.global_library_routes import lib_bp
    from app.routes.group_routes import group_bp
    from app.routes.benchmark_routes import bench_bp
    app.register_blueprint(landing_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(bo_bp)
    app.register_blueprint(res_api_bp)
    app.register_blueprint(lib_bp)
    app.register_blueprint(group_bp)
    app.register_blueprint(bench_bp)

    from app.utils.feature_flags import init_feature_flags
    init_feature_flags(app)

    @app.route('/favicon.ico')
    def _favicon():
        return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/x-icon')

    # ── Health + readiness endpoints ─────────────────────────────────────────
    @app.route('/health')
    def _health():
        return jsonify(status='ok'), 200

    @app.route('/health/ready')
    def _ready():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='ok', db='ok'), 200
        except Exception as e:
            return jsonify(status='degraded', db=str(e)), 503

    return app
