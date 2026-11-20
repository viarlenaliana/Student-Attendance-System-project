"""Khởi tạo ứng dụng Flask cho Student Attendance System."""
import os
from flask import Flask

from app.models.academic import init_academic_tables
from app.routes.academic import academic_bp
from app.routes.schedule import schedule_bp


def create_app(test_config=None):
    """Factory function tạo và cấu hình Flask app theo kiến trúc hệ thống."""
    app = Flask(__name__, template_folder="templates")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-attendance-secret-key-2026"),
        DATABASE_TYPE=os.environ.get("DATABASE_TYPE", "mysql"),
        MYSQL_HOST=os.environ.get("MYSQL_HOST", "localhost"),
        MYSQL_PORT=int(os.environ.get("MYSQL_PORT", 3306)),
        MYSQL_USER=os.environ.get("MYSQL_USER", "root"),
        MYSQL_PASSWORD=os.environ.get("MYSQL_PASSWORD", ""),
        MYSQL_DB=os.environ.get("MYSQL_DB", "student_attendance"),
    )

    if test_config:
        app.config.update(test_config)

    # Đăng ký các Blueprint
    app.register_blueprint(academic_bp)
    app.register_blueprint(schedule_bp)

    # Khởi tạo bảng dữ liệu khi ứng dụng khởi động
    with app.app_context():
        try:
            init_academic_tables()
        except Exception as e:
            app.logger.warning(f"Chưa thể tự động khởi tạo bảng: {e}")

    return app
