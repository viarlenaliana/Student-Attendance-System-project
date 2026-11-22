"""Kiểm thử tự động cho luồng tài khoản, bảo mật, CSRF, phân quyền, OTP, thông báo, database và activity log."""
import logging
import re

import pytest

from app import create_app
from app.models.activity_log import (
    activity_log_error,
    delete_activity_log,
    get_activity_logs,
    update_activity_log,
)
from app.models.database import database_error, fetch_one, get_db_connection
from app.models.notification import (
    create_notification,
    get_unread_notification_count,
    get_user_notifications,
    notify_attendance_result_event,
    notify_attendance_session_event,
    notify_complaint_response_event,
    notify_schedule_event,
)
from app.models.user import (
    auth_error,
    change_password,
    check_password,
    check_user_permission,
    create_password_otp,
    create_user,
    get_current_user,
    get_user_by_username,
    hash_password,
    login_user,
    logout_user,
    reset_password,
    set_user_status,
    verify_password_otp,
)


@pytest.fixture()
def app(tmp_path):
    db_file = tmp_path / "test_attendance.db"
    flask_app = create_app(
        {
            "TESTING": True,
            "CSRF_ENABLED": True,
            "DATABASE_TYPE": "sqlite",
            "SQLITE_DB_PATH": str(db_file),
            "SECRET_KEY": "test-secret-key",
            "MAIL_ENABLED": True,
            "MAIL_SUPPRESS_SEND": True,
            "OTP_RESEND_COOLDOWN_SECONDS": 0,
            "OTP_MAX_ATTEMPTS": 5,
        }
    )
    with flask_app.app_context():
        create_user(
            {
                "username": "admin_test",
                "full_name": "Admin Test",
                "email": "admin.test@example.com",
                "role": "admin",
                "password": "AdminPass123",
                "must_change_password": False,
            }
        )
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _extract_csrf_token(client, page_url="/login"):
    response = client.get(page_url)
    match = re.search(rb'name="csrf_token"\s+value="([^"]+)"', response.data)
    if match:
        return match.group(1).decode("utf-8")
    with client.session_transaction() as sess:
        return sess.get("_csrf_token", "")


def _post_with_csrf(client, url, data=None, token_source_url="/login", follow_redirects=False):
    payload = dict(data or {})
    if "csrf_token" not in payload:
        payload["csrf_token"] = _extract_csrf_token(client, token_source_url)
    return client.post(url, data=payload, follow_redirects=follow_redirects)


def _login_via_client(client, username, password):
    return _post_with_csrf(
        client,
        "/login",
        data={"username": username, "password": password},
        token_source_url="/login",
        follow_redirects=False,
    )


def test_password_hashing_and_no_plaintext_exposure(app):
    with app.app_context():
        created = create_user(
            {
                "username": "sv_hash_01",
                "full_name": "Nguyen Van A",
                "email": "sv.hash01@example.com",
                "role": "student",
                "password": "StudentPass123",
            }
        )
        assert "password_hash" not in created
        assert "password" not in created

        raw_row = fetch_one("SELECT password_hash FROM users WHERE user_id = ?", (created["user_id"],))
        assert raw_row["password_hash"] != "StudentPass123"
        assert check_password("StudentPass123", raw_row["password_hash"])
        assert not check_password("WrongPass123", raw_row["password_hash"])
        assert hash_password("StudentPass123") != raw_row["password_hash"]


def test_no_self_registration_route(client):
    response = client.get("/register")
    assert response.status_code == 404


def test_static_app_js_served_and_contains_expected_handlers(client):
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert b"data-toggle-password" in response.data
    assert b"data-confirm-password-form" in response.data


def test_csrf_protection_enforced_on_all_post_routes(app, client):
    # Thiếu CSRF token khi POST -> 400 Bad Request
    assert client.post("/login", data={"username": "admin_test", "password": "AdminPass123"}).status_code == 400
    assert client.post("/forgot-password", data={"email": "admin.test@example.com"}).status_code == 400
    assert client.post("/verify-otp", data={"email": "admin.test@example.com", "otp": "123456"}).status_code == 400
    assert client.post("/reset-password", data={"new_password": "Abc12345"}).status_code == 400

    # Sai CSRF token -> 400 Bad Request
    client.get("/login")
    assert (
        client.post(
            "/login",
            data={"username": "admin_test", "password": "AdminPass123", "csrf_token": "invalid-token"},
        ).status_code
        == 400
    )

    # Đăng nhập hợp lệ và kiểm tra các route POST sau đăng nhập thiếu CSRF đều trả 400
    assert _login_via_client(client, "admin_test", "AdminPass123").status_code == 302
    assert client.post("/change-password", data={}).status_code == 400
    assert client.post("/admin/users/create", data={}).status_code == 400
    assert client.post("/admin/users/1/update", data={}).status_code == 400
    assert client.post("/admin/users/1/status", data={"is_active": "0"}).status_code == 400
    assert client.post("/notifications/read-all").status_code == 400
    assert client.post("/notifications/1/read").status_code == 400
    assert client.post("/logout").status_code == 400


def test_admin_manage_student_lecturer_and_rbac(app, client):
    # Chưa đăng nhập bị từ chối truy cập trang quản trị
    assert client.get("/admin/users").status_code == 302

    # Đăng nhập Admin
    login_resp = _login_via_client(client, "admin_test", "AdminPass123")
    assert login_resp.status_code == 302
    assert "/admin/users" in login_resp.headers["Location"]

    # Admin tạo Student và Lecturer
    resp_student = _post_with_csrf(
        client,
        "/admin/users/create",
        data={
            "username": "sv001",
            "full_name": "Tran Thi B",
            "email": "sv001@example.com",
            "role": "student",
            "password": "InitPass123",
        },
        token_source_url="/admin/users",
        follow_redirects=True,
    )
    assert resp_student.status_code == 200
    assert b"sv001" in resp_student.data
    assert b"InitPass123" not in resp_student.data

    resp_lecturer = _post_with_csrf(
        client,
        "/admin/users/create",
        data={
            "username": "gv001",
            "full_name": "Le Van C",
            "email": "gv001@example.com",
            "role": "lecturer",
            "password": "LectPass123",
        },
        token_source_url="/admin/users",
        follow_redirects=True,
    )
    assert resp_lecturer.status_code == 200
    assert b"gv001" in resp_lecturer.data

    with app.app_context():
        student = get_user_by_username("sv001")
        lecturer = get_user_by_username("gv001")
        admin_user = get_user_by_username("admin_test")
        second_admin = create_user(
            {
                "username": "admin_second",
                "full_name": "Second Admin",
                "email": "admin.second@example.com",
                "role": "admin",
                "password": "AdminPass123",
                "must_change_password": False,
            }
        )
        assert student is not None and student["must_change_password"] is True
        assert lecturer is not None and lecturer["role"] == "lecturer"
        assert check_user_permission(student["user_id"], "student")
        assert not check_user_permission(student["user_id"], "admin")

    # Kiểm tra ghi log thất bại khi tự khóa tài khoản hoặc thao tác khóa/mở khóa tài khoản Admin
    _post_with_csrf(
        client,
        f"/admin/users/{admin_user['user_id']}/status",
        data={"is_active": "0"},
        token_source_url="/admin/users",
    )
    _post_with_csrf(
        client,
        f"/admin/users/{second_admin['user_id']}/status",
        data={"is_active": "0"},
        token_source_url="/admin/users",
    )
    with app.app_context():
        failed_self_lock = [
            entry
            for entry in get_activity_logs({"action": "lock_user", "result": "failed"})
            if str(entry["object_id"]) == str(admin_user["user_id"])
        ]
        failed_admin_lock = [
            entry
            for entry in get_activity_logs({"action": "lock_user", "result": "failed"})
            if str(entry["object_id"]) == str(second_admin["user_id"])
        ]
        assert len(failed_self_lock) >= 1
        assert len(failed_admin_lock) >= 1

    # Admin cập nhật Student
    resp_update = _post_with_csrf(
        client,
        f"/admin/users/{student['user_id']}/update",
        data={
            "full_name": "Tran Thi B Updated",
            "email": "sv001.new@example.com",
            "role": "student",
        },
        token_source_url="/admin/users",
        follow_redirects=True,
    )
    assert resp_update.status_code == 200
    assert "Tran Thi B Updated".encode("utf-8") in resp_update.data

    # Admin khóa tài khoản Student
    resp_lock = _post_with_csrf(
        client,
        f"/admin/users/{student['user_id']}/status",
        data={"is_active": "0"},
        token_source_url="/admin/users",
        follow_redirects=True,
    )
    assert resp_lock.status_code == 200

    # Đăng xuất Admin, Student bị khóa không đăng nhập được
    _post_with_csrf(client, "/logout", token_source_url="/admin/users")
    locked_login = _login_via_client(client, "sv001", "InitPass123")
    assert locked_login.status_code == 401

    # Admin mở khóa lại Student
    _login_via_client(client, "admin_test", "AdminPass123")
    _post_with_csrf(
        client,
        f"/admin/users/{student['user_id']}/status",
        data={"is_active": "1"},
        token_source_url="/admin/users",
    )
    _post_with_csrf(client, "/logout", token_source_url="/admin/users")

    # Student đăng nhập lần đầu -> bắt buộc đổi mật khẩu
    first_login = _login_via_client(client, "sv001", "InitPass123")
    assert first_login.status_code == 302
    assert "/change-password" in first_login.headers["Location"]

    # Chưa đổi mật khẩu thì bị chặn truy cập dashboard và notifications
    assert "/change-password" in client.get("/dashboard").headers["Location"]
    assert "/change-password" in client.get("/notifications").headers["Location"]

    # Đổi mật khẩu sai mật khẩu cũ -> lỗi
    bad_change = _post_with_csrf(
        client,
        "/change-password",
        data={
            "old_password": "WrongOld123",
            "new_password": "NewStudentPass123",
            "confirm_password": "NewStudentPass123",
        },
        token_source_url="/change-password",
    )
    assert bad_change.status_code == 400

    # Đổi mật khẩu hợp lệ -> thành công
    good_change = _post_with_csrf(
        client,
        "/change-password",
        data={
            "old_password": "InitPass123",
            "new_password": "NewStudentPass123",
            "confirm_password": "NewStudentPass123",
        },
        token_source_url="/change-password",
        follow_redirects=False,
    )
    assert good_change.status_code == 302
    assert "/dashboard" in good_change.headers["Location"]

    # Student truy cập trang Admin -> 403 Forbidden
    assert client.get("/admin/users").status_code == 403
    assert _post_with_csrf(client, "/admin/users/create", data={}, token_source_url="/dashboard").status_code == 403
    assert client.get("/admin/activity-logs").status_code == 403


def test_forgot_password_otp_flow_and_security(app, client):
    with app.app_context():
        create_user(
            {
                "username": "sv_otp",
                "full_name": "Pham Van D",
                "email": "sv.otp@example.com",
                "role": "student",
                "password": "OldOtpPass123",
                "must_change_password": False,
            }
        )

    # Chưa xác minh OTP thì không thể vào trang reset-password
    blocked_reset = client.get("/reset-password")
    assert blocked_reset.status_code == 302
    assert "/verify-otp" in blocked_reset.headers["Location"]

    # Yêu cầu OTP
    req_resp = _post_with_csrf(
        client,
        "/forgot-password",
        data={"email": "sv.otp@example.com"},
        token_source_url="/forgot-password",
        follow_redirects=False,
    )
    assert req_resp.status_code == 302
    assert "/verify-otp" in req_resp.headers["Location"]

    outbox = app.extensions["test_email_outbox"]
    assert len(outbox) == 1
    otp_match = re.search(r"\b(\d{6})\b", outbox[0]["body_text"])
    assert otp_match is not None
    real_otp = otp_match.group(1)

    # Kiểm tra DB không lưu OTP dạng plaintext
    with app.app_context():
        otp_row = fetch_one("SELECT otp_hash FROM password_otps WHERE email = ?", ("sv.otp@example.com",))
        assert otp_row["otp_hash"] != real_otp

        # Chưa gọi verify_password_otp thì reset_password trực tiếp phải thất bại
        with pytest.raises(auth_error):
            reset_password("sv.otp@example.com", real_otp, "BrandNewPass123")

    # Nhập sai OTP -> thất bại
    wrong_otp_resp = _post_with_csrf(
        client,
        "/verify-otp",
        data={"email": "sv.otp@example.com", "otp": "000000"},
        token_source_url="/verify-otp",
    )
    assert wrong_otp_resp.status_code == 400
    assert real_otp.encode("utf-8") not in wrong_otp_resp.data

    # Nhập đúng OTP -> cho phép sang /reset-password
    ok_otp_resp = _post_with_csrf(
        client,
        "/verify-otp",
        data={"email": "sv.otp@example.com", "otp": real_otp},
        token_source_url="/verify-otp",
        follow_redirects=False,
    )
    assert ok_otp_resp.status_code == 302
    assert "/reset-password" in ok_otp_resp.headers["Location"]

    # Đặt lại mật khẩu mới
    reset_resp = _post_with_csrf(
        client,
        "/reset-password",
        data={"new_password": "ResetSuccess123", "confirm_password": "ResetSuccess123"},
        token_source_url="/reset-password",
        follow_redirects=False,
    )
    assert reset_resp.status_code == 302
    assert "/login" in reset_resp.headers["Location"]

    # Đăng nhập với mật khẩu mới thành công
    login_new = _login_via_client(client, "sv_otp", "ResetSuccess123")
    assert login_new.status_code == 302
    assert "/dashboard" in login_new.headers["Location"]

    # OTP đã dùng không thể xác minh lại
    with app.app_context():
        assert verify_password_otp("sv.otp@example.com", real_otp) is False


def test_otp_max_attempts_invalidation(app):
    with app.app_context():
        create_user(
            {
                "username": "sv_otp_limit",
                "full_name": "Hoang Thi E",
                "email": "sv.limit@example.com",
                "role": "student",
                "password": "InitOtpPass123",
                "must_change_password": False,
            }
        )
        create_password_otp("sv.limit@example.com")
        outbox = app.extensions["test_email_outbox"]
        real_otp = re.search(r"\b(\d{6})\b", outbox[-1]["body_text"]).group(1)
        wrong_otp = "999999" if real_otp != "999999" else "888888"

        for _ in range(5):
            assert verify_password_otp("sv.limit@example.com", wrong_otp) is False

        # Sau 5 lần sai, kể cả nhập đúng OTP cũng bị vô hiệu hóa
        assert verify_password_otp("sv.limit@example.com", real_otp) is False


def test_notifications_all_four_events_and_ownership(app, client):
    with app.app_context():
        student1 = create_user(
            {
                "username": "sv_notif1",
                "full_name": "Student One",
                "email": "sv.notif1@example.com",
                "role": "student",
                "password": "UserPass123",
                "must_change_password": False,
            }
        )
        create_user(
            {
                "username": "sv_notif2",
                "full_name": "Student Two",
                "email": "sv.notif2@example.com",
                "role": "student",
                "password": "UserPass123",
                "must_change_password": False,
            }
        )

        notify_schedule_event(
            [student1["user_id"]],
            {"schedule_id": 10, "class_name": "SE101", "schedule_date": "2026-11-25", "start_time": "07:30", "end_time": "09:30"},
            event_action="created",
        )
        notify_attendance_session_event(
            [student1["user_id"]],
            {"session_id": 22, "class_name": "SE101", "attendance_method": "QR code", "session_date": "2026-11-25"},
            event_action="opened",
        )
        notify_attendance_result_event(
            student1["user_id"],
            {"attendance_id": 55, "session_id": 22, "class_name": "SE101", "status": "Present"},
        )
        notify_complaint_response_event(
            student1["user_id"],
            {"complaint_id": 7, "status": "Accepted", "class_name": "SE101", "lecturer_response": "Đã cập nhật trạng thái"},
        )

        notifications = get_user_notifications(student1["user_id"])
        assert len(notifications) == 4
        assert {item["notification_type"] for item in notifications} == {
            "schedule",
            "attendance_session",
            "attendance_result",
            "complaint_response",
        }
        assert all(item["email_status"] == "sent" for item in notifications)
        assert get_unread_notification_count(student1["user_id"]) == 4

        outbox = app.extensions["test_email_outbox"]
        assert len(outbox) == 4

        target_notif_id = notifications[0]["notification_id"]

    # Student 2 không được phép đánh dấu đã đọc thông báo của Student 1
    _login_via_client(client, "sv_notif2", "UserPass123")
    forbidden_read = _post_with_csrf(
        client,
        f"/notifications/{target_notif_id}/read",
        token_source_url="/notifications",
    )
    assert forbidden_read.status_code == 403
    _post_with_csrf(client, "/logout", token_source_url="/notifications")

    # Student 1 xem và đánh dấu đã đọc
    _login_via_client(client, "sv_notif1", "UserPass123")
    page_resp = client.get("/notifications")
    assert page_resp.status_code == 200
    assert b"SE101" in page_resp.data

    _post_with_csrf(
        client,
        f"/notifications/{target_notif_id}/read",
        token_source_url="/notifications",
    )
    with app.app_context():
        assert get_unread_notification_count(student1["user_id"]) == 3

    _post_with_csrf(client, "/notifications/read-all", token_source_url="/notifications")
    with app.app_context():
        assert get_unread_notification_count(student1["user_id"]) == 0


def test_activity_log_recording_date_to_filter_and_immutability(app, client):
    with app.app_context():
        create_user(
            {
                "username": "gv_log_test",
                "full_name": "Lecturer Log",
                "email": "gv.log@example.com",
                "role": "lecturer",
                "password": "LectPass123",
                "must_change_password": False,
            }
        )

    _login_via_client(client, "gv_log_test", "LectPass123")
    # Lecturer không được xem hoặc sửa/xóa log
    assert client.get("/admin/activity-logs").status_code == 403
    assert _post_with_csrf(client, "/admin/activity-logs/1/edit", token_source_url="/dashboard").status_code == 403
    assert _post_with_csrf(client, "/admin/activity-logs/1/delete", token_source_url="/dashboard").status_code == 403
    _post_with_csrf(client, "/logout", token_source_url="/dashboard")

    # Admin xem được log và giao diện có cả bộ lọc date_from và date_to
    _login_via_client(client, "admin_test", "AdminPass123")
    logs_resp = client.get("/admin/activity-logs?date_from=2020-01-01&date_to=2099-12-31")
    assert logs_resp.status_code == 200
    assert b"gv_log_test" in logs_resp.data
    assert b'name="date_to"' in logs_resp.data

    # Lọc với khoảng ngày quá khứ không có dữ liệu -> không hiển thị gv_log_test
    empty_logs_resp = client.get("/admin/activity-logs?date_from=2000-01-01&date_to=2000-01-02")
    assert empty_logs_resp.status_code == 200
    assert b"gv_log_test" not in empty_logs_resp.data

    with app.app_context():
        logs = get_activity_logs({"username": "gv_log_test"})
        actions = {entry["action"] for entry in logs}
        assert "login" in actions
        assert "logout" in actions

        # Hàm model cũng cấm sửa/xóa
        with pytest.raises(activity_log_error):
            update_activity_log(1, {"result": "failed"})
        with pytest.raises(activity_log_error):
            delete_activity_log(1)


def test_mysql_failure_does_not_fallback_to_sqlite(tmp_path):
    sqlite_fallback_path = tmp_path / "should_not_exist.db"
    with pytest.raises(database_error) as exc_info:
        create_app(
            {
                "TESTING": True,
                "DATABASE_TYPE": "mysql",
                "MYSQL_HOST": "127.0.0.1",
                "MYSQL_PORT": 39999,
                "MYSQL_USER": "root",
                "MYSQL_PASSWORD": "wrong-password-secret",
                "MYSQL_DB": "student_attendance",
                "SQLITE_DB_PATH": str(sqlite_fallback_path),
            }
        )
    message = str(exc_info.value)
    assert "MySQL" in message
    assert "wrong-password-secret" not in message
    assert not sqlite_fallback_path.exists()


def test_app_startup_logs_optional_modules_and_registered_blueprints(tmp_path, caplog):
    db_file = tmp_path / "log_check.db"
    with caplog.at_level(logging.INFO):
        flask_app = create_app(
            {
                "TESTING": True,
                "DATABASE_TYPE": "sqlite",
                "SQLITE_DB_PATH": str(db_file),
                "SECRET_KEY": "test-secret-key",
            }
        )
    assert set(["auth", "admin_users", "notification", "activity_log"]).issubset(flask_app.blueprints.keys())
    log_text = caplog.text
    assert "Academic" in log_text
    assert "Schedule" in log_text
    assert "init_account_system_tables" in log_text or "Đã khởi tạo các bảng hệ thống" in log_text


def test_model_session_helpers_directly(app):
    with app.app_context():
        user = create_user(
            {
                "username": "sv_direct",
                "full_name": "Direct Model User",
                "email": "sv.direct@example.com",
                "role": "student",
                "password": "DirectPass123",
                "must_change_password": True,
            }
        )
        with app.test_request_context("/login"):
            logged = login_user("sv_direct", "DirectPass123")
            assert logged["user_id"] == user["user_id"]
            assert get_current_user()["username"] == "sv_direct"
            assert change_password(user["user_id"], "DirectPass123", "DirectPass456") is True
            assert get_current_user()["must_change_password"] is False
            logout_user()
            assert get_current_user() is None

        # Khóa user và kiểm tra permission
        assert set_user_status(user["user_id"], False) is True
        assert check_user_permission(user["user_id"], "student") is False
        # Gửi notification trực tiếp với 4 tham số như module khác gọi
        notif = create_notification(user["user_id"], "Lịch học mới", "SE101 - 2026-11-25", "schedule")
        assert notif["notification_type"] == "schedule"
