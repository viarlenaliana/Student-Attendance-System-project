from flask import Flask
from config import Config
from app.extensions import db


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(Config)

    # Initialize database
    db.init_app(app)
    # Import models
    from app import models

    # Register routes
    from app.routes.main_routes import main_bp
    from app.routes.auth import auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    return app