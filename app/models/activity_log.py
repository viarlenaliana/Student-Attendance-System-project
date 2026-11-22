"""Quản lý nhật ký hoạt động (Activity Log) của hệ thống.

Ghi nhận đăng nhập thành công và các hoạt động quan trọng kèm tài khoản,
thời gian, hành động, đối tượng bị tác động và kết quả.
Người dùng thông thường không được xem, sửa hoặc xóa nhật ký hoạt động.
"""
import logging

from flask import has_request_context, request

from app.models.database import fetch_all, fetch_one, now_text, run_write

logger = logging.getLogger(__name__)

VALID_LOG_RESULTS = ("success", "failed")


class activity_log_error(Exception):
    """Lỗi nghiệp vụ hoặc phân quyền đối với nhật ký hoạt động."""


def create_activity_log(
    user_id,
    action,
    object_type,
    object_id=None,
    result="success",
    details=None,
    ip_address=None,
    username=None,
):
    """Ghi nhận một bản ghi nhật ký hoạt động mới (chỉ cho phép thêm mới, không sửa/xóa)."""
    clean_action = (action or "").strip() or "unknown_action"
    clean_object_type = (object_type or "").strip() or "system"
    clean_result = (result or "success").strip().lower()
    if clean_result not in VALID_LOG_RESULTS:
        clean_result = "success"

    resolved_user_id = None
    if user_id is not None:
        try:
            resolved_user_id = int(user_id)
        except (TypeError, ValueError):
            resolved_user_id = None

    resolved_username = (username or "").strip() or None
    if resolved_username is None and resolved_user_id is not None:
        user_row = fetch_one("SELECT username FROM users WHERE user_id = ?", (resolved_user_id,))
        if user_row:
            resolved_username = user_row["username"]

    resolved_ip = ip_address
    if resolved_ip is None and has_request_context():
        resolved_ip = request.remote_addr

    clean_object_id = str(object_id) if object_id is not None else None
    clean_details = (details or "").strip() or None

    try:
        log_id = run_write(
            """
            INSERT INTO activity_logs (
                user_id, username, action, object_type, object_id,
                result, details, ip_address, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_user_id,
                resolved_username,
                clean_action,
                clean_object_type,
                clean_object_id,
                clean_result,
                clean_details,
                resolved_ip,
                now_text(),
            ),
        )
        return get_activity_log_by_id(log_id)
    except Exception as error:
        logger.warning("Không thể ghi activity log (%s): %s", clean_action, type(error).__name__)
        return None


def get_activity_log_by_id(log_id):
    """Truy vấn chi tiết một bản ghi activity log theo log_id."""
    return fetch_one(
        """
        SELECT activity_logs.*,
               COALESCE(users.username, activity_logs.username) AS account_username,
               users.full_name,
               users.role
        FROM activity_logs
        LEFT JOIN users ON users.user_id = activity_logs.user_id
        WHERE activity_logs.log_id = ?
        """,
        (log_id,),
    )


def get_activity_logs(filters=None, limit=200):
    """Truy vấn danh sách activity log kèm bộ lọc (chỉ dành cho Admin)."""
    filters = filters or {}
    sql_query = """
        SELECT activity_logs.*,
               COALESCE(users.username, activity_logs.username) AS account_username,
               users.full_name,
               users.role
        FROM activity_logs
        LEFT JOIN users ON users.user_id = activity_logs.user_id
        WHERE 1 = 1
    """
    params = []

    if filters.get("user_id"):
        try:
            params.append(int(filters["user_id"]))
            sql_query += " AND activity_logs.user_id = ?"
        except (TypeError, ValueError):
            pass

    if filters.get("username"):
        keyword = "%" + str(filters["username"]).strip() + "%"
        sql_query += " AND (activity_logs.username LIKE ? OR users.username LIKE ?)"
        params.extend([keyword, keyword])

    if filters.get("action"):
        sql_query += " AND activity_logs.action = ?"
        params.append(str(filters["action"]).strip())

    if filters.get("object_type"):
        sql_query += " AND activity_logs.object_type = ?"
        params.append(str(filters["object_type"]).strip())

    if filters.get("result"):
        sql_query += " AND activity_logs.result = ?"
        params.append(str(filters["result"]).strip().lower())

    if filters.get("date_from"):
        sql_query += " AND activity_logs.created_at >= ?"
        params.append(str(filters["date_from"]).strip() + " 00:00:00")

    if filters.get("date_to"):
        sql_query += " AND activity_logs.created_at <= ?"
        params.append(str(filters["date_to"]).strip() + " 23:59:59")

    safe_limit = max(1, min(int(limit or 200), 1000))
    sql_query += " ORDER BY activity_logs.log_id DESC LIMIT ?"
    params.append(safe_limit)
    return fetch_all(sql_query, tuple(params))


def get_distinct_log_actions():
    """Lấy danh sách các hành động đã ghi nhận để hiển thị bộ lọc."""
    rows = fetch_all("SELECT DISTINCT action FROM activity_logs ORDER BY action")
    return [row["action"] for row in rows]


def get_distinct_log_object_types():
    """Lấy danh sách các loại đối tượng đã ghi nhận để hiển thị bộ lọc."""
    rows = fetch_all("SELECT DISTINCT object_type FROM activity_logs ORDER BY object_type")
    return [row["object_type"] for row in rows]


def update_activity_log(*_args, **_kwargs):
    """Chặn tuyệt đối mọi thao tác chỉnh sửa nhật ký hoạt động."""
    raise activity_log_error("Nhật ký hoạt động được bảo vệ, không được phép chỉnh sửa.")


def delete_activity_log(*_args, **_kwargs):
    """Chặn tuyệt đối mọi thao tác xóa nhật ký hoạt động."""
    raise activity_log_error("Nhật ký hoạt động được bảo vệ, không được phép xóa.")
