import os

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from app.config import Config


def create_app():
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = Config.JWT_SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_UPLOAD_MB * 1024 * 1024
    JWTManager(app)
    CORS(app, resources={r"/api/*": {"origins": Config.FRONTEND_ORIGIN}})

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    from app.routes.health import health_bp
    app.register_blueprint(health_bp)

    from app.routes.db_health import db_health_bp
    app.register_blueprint(db_health_bp)

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.prescriptions import prescriptions_bp
    app.register_blueprint(prescriptions_bp)

    from app.routes.clinical_decision import clinical_decision_bp
    app.register_blueprint(clinical_decision_bp)

    from app.routes.price_comparison import price_comparison_bp
    app.register_blueprint(price_comparison_bp)

    from app.routes.generic_recommendation import generic_recommendation_bp
    app.register_blueprint(generic_recommendation_bp)

    from app.routes.offers import offers_bp
    app.register_blueprint(offers_bp)

    from app.routes.data_sources import data_sources_bp
    app.register_blueprint(data_sources_bp)

    from app.routes.scan import scan_bp
    app.register_blueprint(scan_bp)

    from app.routes.stores import stores_bp
    app.register_blueprint(stores_bp)

    from app.routes.feeds import feeds_bp
    app.register_blueprint(feeds_bp)

    @app.errorhandler(413)
    def file_too_large(_e):
        return jsonify({"error": f"file exceeds the {Config.MAX_UPLOAD_MB}MB upload limit"}), 413

    return app