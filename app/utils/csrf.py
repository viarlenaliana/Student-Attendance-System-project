"""Tiện ích bảo vệ CSRF (Cross-Site Request Forgery) dùng chung cho các form POST."""
import hmac
import secrets

from flask import session


CSRF_PROTECTED_BLUEPRINTS = ("auth", "admin_users", "notification", "activity_log")


def generate_csrf_token():
    """Tạo hoặc lấy CSRF token gắn với phiên làm việc hiện tại."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token(submitted_token):
    """Kiểm tra CSRF token gửi lên có khớp với token trong session hay không."""
    expected_token = session.get("_csrf_token")
    if not expected_token or not submitted_token:
        return False
    return hmac.compare_digest(str(expected_token), str(submitted_token))
