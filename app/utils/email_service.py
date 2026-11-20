"""Dịch vụ gửi email qua SMTP cho OTP và thông báo hệ thống.

Không lưu mật khẩu SMTP thật trong mã nguồn; luôn đọc cấu hình từ Flask config / biến môi trường.
Không ghi nội dung OTP hoặc mật khẩu vào log ứng dụng.
"""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)


def get_mail_settings():
    """Đọc cấu hình SMTP từ current_app.config."""
    config = current_app.config if has_app_context() else {}
    return {
        "mail_enabled": bool(config.get("MAIL_ENABLED", False)),
        "mail_suppress_send": bool(config.get("MAIL_SUPPRESS_SEND", False)),
        "mail_server": config.get("MAIL_SERVER", "smtp.gmail.com"),
        "mail_port": int(config.get("MAIL_PORT", 587)),
        "mail_use_tls": bool(config.get("MAIL_USE_TLS", True)),
        "mail_use_ssl": bool(config.get("MAIL_USE_SSL", False)),
        "mail_username": config.get("MAIL_USERNAME", ""),
        "mail_password": config.get("MAIL_PASSWORD", ""),
        "mail_default_sender": config.get("MAIL_DEFAULT_SENDER") or config.get("MAIL_USERNAME", ""),
        "mail_timeout_seconds": int(config.get("MAIL_TIMEOUT_SECONDS", 10)),
        "is_testing": bool(config.get("TESTING", False)),
    }


def _record_test_outbox(recipient_email, subject, body_text):
    """Lưu bản sao email vào outbox bộ nhớ chỉ khi đang chạy automated test."""
    if has_app_context() and current_app.config.get("TESTING"):
        outbox = current_app.extensions.setdefault("test_email_outbox", [])
        outbox.append(
            {
                "recipient_email": recipient_email,
                "subject": subject,
                "body_text": body_text,
            }
        )


def send_email(recipient_email, subject, body_text, body_html=None):
    """Gửi email văn bản/HTML qua SMTP. Trả về dict trạng thái ('sent', 'skipped', 'failed')."""
    if not recipient_email:
        return {"status": "skipped", "reason": "Thiếu địa chỉ email người nhận."}

    settings = get_mail_settings()

    if settings["is_testing"] and settings["mail_suppress_send"]:
        _record_test_outbox(recipient_email, subject, body_text)
        return {"status": "sent", "reason": "Đã ghi nhận trong chế độ kiểm thử."}

    if not settings["mail_enabled"] or settings["mail_suppress_send"]:
        if settings["is_testing"]:
            _record_test_outbox(recipient_email, subject, body_text)
        return {"status": "skipped", "reason": "Chưa bật gửi email SMTP (MAIL_ENABLED=false)."}

    if not settings["mail_server"] or not settings["mail_username"] or not settings["mail_password"]:
        return {"status": "failed", "reason": "Thiếu thông tin cấu hình SMTP (MAIL_USERNAME/MAIL_PASSWORD)."}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings["mail_default_sender"] or settings["mail_username"]
    message["To"] = recipient_email
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    try:
        if settings["mail_use_ssl"]:
            with smtplib.SMTP_SSL(
                settings["mail_server"],
                settings["mail_port"],
                timeout=settings["mail_timeout_seconds"],
            ) as smtp_client:
                smtp_client.login(settings["mail_username"], settings["mail_password"])
                smtp_client.send_message(message)
        else:
            with smtplib.SMTP(
                settings["mail_server"],
                settings["mail_port"],
                timeout=settings["mail_timeout_seconds"],
            ) as smtp_client:
                if settings["mail_use_tls"]:
                    smtp_client.starttls()
                smtp_client.login(settings["mail_username"], settings["mail_password"])
                smtp_client.send_message(message)
        return {"status": "sent", "reason": "Đã gửi email thành công."}
    except Exception as error:
        logger.warning("Không thể gửi email tới %s: %s", recipient_email, type(error).__name__)
        return {"status": "failed", "reason": f"Lỗi kết nối SMTP ({type(error).__name__})."}


def send_otp_email(recipient_email, full_name, otp_code, expiry_minutes):
    """Gửi email chứa mã OTP khôi phục mật khẩu tới email đã đăng ký."""
    display_name = full_name or "Người dùng"
    subject = "[Student Attendance System] Mã OTP khôi phục mật khẩu"
    body_text = (
        f"Xin chào {display_name},\n\n"
        f"Bạn vừa yêu cầu đặt lại mật khẩu trên hệ thống Student Attendance System.\n"
        f"Mã xác thực OTP của bạn là: {otp_code}\n"
        f"Mã có hiệu lực trong {expiry_minutes} phút và chỉ sử dụng một lần.\n\n"
        f"Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email và liên hệ quản trị viên.\n"
    )
    return send_email(recipient_email, subject, body_text)


def send_notification_email(recipient_email, full_name, title, message_content, notification_type):
    """Gửi email thông báo sự kiện hệ thống (lịch học, điểm danh, khiếu nại)."""
    type_labels = {
        "schedule": "Lịch học",
        "attendance_session": "Buổi điểm danh",
        "attendance_result": "Kết quả điểm danh",
        "complaint_response": "Phản hồi khiếu nại",
        "system": "Hệ thống",
    }
    type_label = type_labels.get(notification_type, "Thông báo")
    display_name = full_name or "Người dùng"
    subject = f"[Student Attendance System - {type_label}] {title}"
    body_text = (
        f"Xin chào {display_name},\n\n"
        f"Loại thông báo: {type_label}\n"
        f"Tiêu đề: {title}\n\n"
        f"{message_content}\n\n"
        f"Vui lòng đăng nhập hệ thống để xem chi tiết.\n"
    )
    return send_email(recipient_email, subject, body_text)
