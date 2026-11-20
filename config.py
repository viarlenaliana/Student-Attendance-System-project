"""Cấu hình ứng dụng Flask cho Student Attendance System."""
import os
from datetime import timedelta

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _parse_bool(raw_value, default_value=False):
    if raw_value is None:
        return default_value
    return str(raw_value).strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Lớp cấu hình chính đọc giá trị từ biến môi trường."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-this-secret-key-in-env")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _parse_bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_LIFETIME_HOURS", 8)))

    # Cơ sở dữ liệu (MySQL ưu tiên theo thống nhất nhóm, SQLite dự phòng khi demo/test)
    DATABASE_TYPE = os.environ.get("DATABASE_TYPE", "mysql")
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DB = os.environ.get("MYSQL_DB", "student_attendance")
    MYSQL_CHARSET = os.environ.get("MYSQL_CHARSET", "utf8mb4")
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "demo.db")

    # Chính sách mật khẩu & OTP
    PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", 8))
    OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", 10))
    OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", 5))
    OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", 60))

    # Cấu hình SMTP gửi email thông báo & OTP (không lưu mật khẩu thật trong mã nguồn)
    MAIL_ENABLED = _parse_bool(os.environ.get("MAIL_ENABLED"), False)
    MAIL_SUPPRESS_SEND = _parse_bool(os.environ.get("MAIL_SUPPRESS_SEND"), False)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = _parse_bool(os.environ.get("MAIL_USE_TLS"), True)
    MAIL_USE_SSL = _parse_bool(os.environ.get("MAIL_USE_SSL"), False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
    MAIL_TIMEOUT_SECONDS = int(os.environ.get("MAIL_TIMEOUT_SECONDS", 10))
