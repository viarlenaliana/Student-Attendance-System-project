from flask import Flask
from config import Config
from app.extensions import db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Import models để SQLAlchemy nhận diện các bảng
    from app import models

    from app.routes.main_routes import main_bp
    app.register_blueprint(main_bp)

    return app