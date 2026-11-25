from flask import Flask
from config import Config
from app.extensions import db


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    db.init_app(app)

    # Import models
    from app import models

    # Import routes
    from app.routes.main_routes import main_bp
    from app.routes.auth import auth_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.lecturer_routes import lecturer_bp

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(lecturer_bp)

    return app