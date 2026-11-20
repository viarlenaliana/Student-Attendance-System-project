"""Quản lý thông báo trong ứng dụng và gửi email thông báo sự kiện.

Hỗ trợ các sự kiện được đặc tả:
- Lịch học ('schedule')
- Buổi điểm danh ('attendance_session')
- Kết quả điểm danh ('attendance_result')
- Phản hồi khiếu nại ('complaint_response')
- Thông báo hệ thống ('system')
"""
import logging

from app.models.database import fetch_all, fetch_one, now_text, run_write
from app.utils.email_service import send_notification_email

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES = (
    "schedule",
    "attendance_session",
    "attendance_result",
    "complaint_response",
    "system",
)

NOTIFICATION_TYPE_LABELS = {
    "schedule": "Lịch học",
    "attendance_session": "Buổi điểm danh",
    "attendance_result": "Kết quả điểm danh",
    "complaint_response": "Phản hồi khiếu nại",
    "system": "Hệ thống",
}


class notification_error(Exception):
    """Lỗi nghiệp vụ khi tạo hoặc thao tác thông báo."""


def create_notification(
    user_id,
    title,
    message,
    notification_type="system",
    related_id=None,
    send_email=True,
):
    """Tạo thông báo trong ứng dụng và gửi email cho người dùng nhận.

    Hàm giữ nguyên chữ ký tương thích với lời gọi từ các module khác:
    create_notification(user_id, title, message, notification_type)
    """
    try:
        target_user_id = int(user_id)
    except (TypeError, ValueError) as error:
        raise notification_error("Mã người nhận thông báo (user_id) không hợp lệ.") from error

    clean_title = (title or "").strip()
    clean_message = (message or "").strip()
    clean_type = (notification_type or "system").strip().lower()

    if not clean_title:
        raise notification_error("Tiêu đề thông báo không được để trống.")
    if not clean_message:
        raise notification_error("Nội dung thông báo không được để trống.")
    if clean_type not in NOTIFICATION_TYPES:
        raise notification_error("Loại thông báo không hợp lệ.")

    user_record = fetch_one(
        "SELECT user_id, full_name, email, is_active FROM users WHERE user_id = ?",
        (target_user_id,),
    )
    if user_record is None:
        raise notification_error("Không tìm thấy tài khoản người nhận thông báo.")

    clean_related_id = None
    if related_id is not None:
        try:
            clean_related_id = int(related_id)
        except (TypeError, ValueError):
            clean_related_id = None

    timestamp_text = now_text()
    notification_id = run_write(
        """
        INSERT INTO notifications (
            user_id, title, message, notification_type, related_id,
            is_read, email_status, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 0, 'pending', 'unread', ?, ?)
        """,
        (
            target_user_id,
            clean_title,
            clean_message,
            clean_type,
            clean_related_id,
            timestamp_text,
            timestamp_text,
        ),
    )

    email_status = "skipped"
    if send_email and user_record.get("is_active") and user_record.get("email"):
        try:
            delivery = send_notification_email(
                user_record["email"],
                user_record.get("full_name"),
                clean_title,
                clean_message,
                clean_type,
            )
            email_status = delivery.get("status", "failed")
        except Exception as error:
            logger.warning("Lỗi gửi email thông báo cho user_id=%s: %s", target_user_id, type(error).__name__)
            email_status = "failed"

    run_write(
        "UPDATE notifications SET email_status = ?, updated_at = ? WHERE notification_id = ?",
        (email_status, now_text(), notification_id),
    )
    return get_notification_by_id(notification_id)


def notify_users(
    user_ids,
    title,
    message,
    notification_type="system",
    related_id=None,
    send_email=True,
):
    """Gửi thông báo tới nhiều user_id, cô lập lỗi từng người nhận."""
    unique_user_ids = []
    seen_ids = set()
    for raw_user_id in user_ids or []:
        if raw_user_id is None or raw_user_id in seen_ids:
            continue
        seen_ids.add(raw_user_id)
        unique_user_ids.append(raw_user_id)

    created_notifications = []
    failed_user_ids = []
    for target_user_id in unique_user_ids:
        try:
            notification = create_notification(
                target_user_id,
                title,
                message,
                notification_type=notification_type,
                related_id=related_id,
                send_email=send_email,
            )
            created_notifications.append(notification)
        except Exception as error:
            logger.warning("Không thể gửi thông báo tới user_id=%s: %s", target_user_id, error)
            failed_user_ids.append(target_user_id)

    return {
        "created_notifications": created_notifications,
        "failed_user_ids": failed_user_ids,
    }


def notify_schedule_event(user_ids, schedule_data, event_action="updated"):
    """Phối hợp với module Lịch học để gửi thông báo sự kiện lịch học."""
    schedule_data = schedule_data or {}
    action_titles = {
        "created": "Lịch học mới",
        "makeup": "Lịch học bù mới",
        "updated": "Lịch học thay đổi",
        "cancelled": "Lịch học bị hủy",
    }
    title = action_titles.get(event_action, "Cập nhật lịch học")
    class_name = schedule_data.get("class_name") or f"Lớp #{schedule_data.get('class_id', '')}"
    schedule_date = schedule_data.get("schedule_date", "")
    start_time = schedule_data.get("start_time", "")
    end_time = schedule_data.get("end_time", "")
    room = schedule_data.get("room")

    parts = [f"Lớp học phần: {class_name}"]
    if schedule_date:
        parts.append(f"Ngày: {schedule_date}")
    if start_time and end_time:
        parts.append(f"Thời gian: {start_time} - {end_time}")
    if room:
        parts.append(f"Phòng học: {room}")
    if event_action == "cancelled" and schedule_data.get("cancel_reason"):
        parts.append(f"Lý do hủy: {schedule_data['cancel_reason']}")

    message = " | ".join(parts)
    return notify_users(
        user_ids,
        title,
        message,
        notification_type="schedule",
        related_id=schedule_data.get("schedule_id"),
    )


def notify_attendance_session_event(user_ids, session_data, event_action="opened"):
    """Phối hợp với module Buổi điểm danh để gửi thông báo mở/đóng/mở lại buổi điểm danh."""
    session_data = session_data or {}
    action_titles = {
        "opened": "Buổi điểm danh đã mở",
        "reopened": "Buổi điểm danh được mở lại",
        "ended": "Buổi điểm danh đã kết thúc",
    }
    title = action_titles.get(event_action, "Cập nhật buổi điểm danh")
    class_name = session_data.get("class_name") or f"Lớp #{session_data.get('class_id', '')}"
    session_id = session_data.get("session_id")
    attendance_method = session_data.get("attendance_method", "")
    session_date = session_data.get("session_date", "")

    parts = [f"Lớp học phần: {class_name}"]
    if session_id is not None:
        parts.append(f"Mã buổi điểm danh: {session_id}")
    if session_date:
        parts.append(f"Ngày: {session_date}")
    if attendance_method:
        parts.append(f"Phương thức: {attendance_method}")

    message = " | ".join(parts)
    return notify_users(
        user_ids,
        title,
        message,
        notification_type="attendance_session",
        related_id=session_id,
    )


def notify_attendance_result_event(user_id, attendance_data):
    """Phối hợp với module Điểm danh để thông báo kết quả điểm danh cho sinh viên."""
    attendance_data = attendance_data or {}
    attendance_status = attendance_data.get("status", "Present")
    class_name = attendance_data.get("class_name") or f"Buổi #{attendance_data.get('session_id', '')}"
    session_id = attendance_data.get("session_id")
    attendance_id = attendance_data.get("attendance_id")
    note = attendance_data.get("note")

    title = f"Kết quả điểm danh: {attendance_status}"
    parts = [
        f"Lớp/Buổi: {class_name}",
        f"Trạng thái: {attendance_status}",
    ]
    if session_id is not None:
        parts.append(f"Mã buổi: {session_id}")
    if note:
        parts.append(f"Ghi chú: {note}")

    message = " | ".join(parts)
    return create_notification(
        user_id,
        title,
        message,
        notification_type="attendance_result",
        related_id=attendance_id or session_id,
    )


def notify_complaint_response_event(user_id, complaint_data):
    """Phối hợp với module Khiếu nại để gửi thông báo phản hồi khiếu nại cho sinh viên."""
    complaint_data = complaint_data or {}
    complaint_id = complaint_data.get("complaint_id")
    complaint_status = complaint_data.get("status", "In Progress")
    lecturer_response = complaint_data.get("lecturer_response") or ""
    class_name = complaint_data.get("class_name")

    title = f"Phản hồi khiếu nại #{complaint_id or ''} ({complaint_status})".strip()
    parts = [f"Trạng thái khiếu nại: {complaint_status}"]
    if class_name:
        parts.append(f"Lớp học phần: {class_name}")
    if lecturer_response:
        parts.append(f"Phản hồi của giảng viên: {lecturer_response}")

    message = " | ".join(parts)
    return create_notification(
        user_id,
        title,
        message,
        notification_type="complaint_response",
        related_id=complaint_id,
    )


def get_notification_by_id(notification_id):
    """Lấy thông tin một thông báo theo notification_id."""
    return fetch_one(
        "SELECT * FROM notifications WHERE notification_id = ?",
        (notification_id,),
    )


def get_user_notifications(user_id, unread_only=False, notification_type=None, limit=100):
    """Lấy danh sách thông báo của người dùng hiện tại."""
    sql_query = "SELECT * FROM notifications WHERE user_id = ?"
    params = [user_id]

    if unread_only:
        sql_query += " AND is_read = 0"
    if notification_type and notification_type in NOTIFICATION_TYPES:
        sql_query += " AND notification_type = ?"
        params.append(notification_type)

    safe_limit = max(1, min(int(limit or 100), 500))
    sql_query += " ORDER BY notification_id DESC LIMIT ?"
    params.append(safe_limit)
    return fetch_all(sql_query, tuple(params))


def get_unread_notification_count(user_id):
    """Đếm số lượng thông báo chưa đọc của người dùng."""
    row = fetch_one(
        "SELECT COUNT(*) AS unread_count FROM notifications WHERE user_id = ? AND is_read = 0",
        (user_id,),
    )
    return int(row["unread_count"]) if row else 0


def mark_notification_as_read(notification_id, user_id):
    """Đánh dấu một thông báo là đã đọc (kiểm tra đúng chủ sở hữu)."""
    notification = get_notification_by_id(notification_id)
    if notification is None:
        raise notification_error("Không tìm thấy thông báo.")
    if int(notification["user_id"]) != int(user_id):
        raise notification_error("Bạn không có quyền thao tác thông báo của người dùng khác.")
    if not notification["is_read"]:
        run_write(
            "UPDATE notifications SET is_read = 1, status = 'read', updated_at = ? WHERE notification_id = ?",
            (now_text(), notification_id),
        )
    return get_notification_by_id(notification_id)


def mark_all_notifications_as_read(user_id):
    """Đánh dấu toàn bộ thông báo của người dùng là đã đọc."""
    run_write(
        "UPDATE notifications SET is_read = 1, status = 'read', updated_at = ? WHERE user_id = ? AND is_read = 0",
        (now_text(), user_id),
    )
    return True
