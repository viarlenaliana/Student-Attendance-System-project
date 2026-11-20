"""Kiểm thử tự động cho luồng tài khoản, bảo mật, phân quyền, OTP, thông báo và activity log."""
import re

import pytest

from app import create_app
from app.models.activity_log import (
    activity_log_error,
    delete_activity_log,
    get_activity_logs,
    update_activity_log,
)
from app.models.database import fetch_one
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


def _login_via_client(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
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


def test_admin_manage_student_lecturer_and_rbac(app, client):
    # Chưa đăng nhập bị từ chối truy cập trang quản trị
    assert client.get("/admin/users").status_code == 302

    # Đăng nhập Admin
    login_resp = _login_via_client(client, "admin_test", "AdminPass123")
    assert login_resp.status_code == 302
    assert "/admin/users" in login_resp.headers["Location"]

    # Admin tạo Student và Lecturer
    resp_student = client.post(
        "/admin/users/create",
        data={
            "username": "sv001",
            "full_name": "Tran Thi B",
            "email": "sv001@example.com",
            "role": "student",
            "password": "InitPass123",
        },
        follow_redirects=True,
    )
    assert resp_student.status_code == 200
    assert b"sv001" in resp_student.data
    assert b"InitPass123" not in resp_student.data  # Không hiển thị mật khẩu chữ thường

    resp_lecturer = client.post(
        "/admin/users/create",
        data={
            "username": "gv001",
            "full_name": "Le Van C",
            "email": "gv001@example.com",
            "role": "lecturer",
            "password": "LectPass123",
        },
        follow_redirects=True,
    )
    assert resp_lecturer.status_code == 200
    assert b"gv001" in resp_lecturer.data

    with app.app_context():
        student = get_user_by_username("sv001")
        lecturer = get_user_by_username("gv001")
        assert student is not None and student["must_change_password"] is True
        assert lecturer is not None and lecturer["role"] == "lecturer"
        assert check_user_permission(student["user_id"], "student")
        assert not check_user_permission(student["user_id"], "admin")

    # Admin cập nhật Student
    resp_update = client.post(
        f"/admin/users/{student['user_id']}/update",
        data={
            "full_name": "Tran Thi B Updated",
            "email": "sv001.new@example.com",
            "role": "student",
        },
        follow_redirects=True,
    )
    assert resp_update.status_code == 200
    assert "Tran Thi B Updated".encode("utf-8") in resp_update.data

    # Admin khóa tài khoản Student
    resp_lock = client.post(
        f"/admin/users/{student['user_id']}/status",
        data={"is_active": "0"},
        follow_redirects=True,
    )
    assert resp_lock.status_code == 200

    # Đăng xuất Admin, Student bị khóa không đăng nhập được
    client.post("/logout")
    locked_login = _login_via_client(client, "sv001", "InitPass123")
    assert locked_login.status_code == 401

    # Admin mở khóa lại Student
    _login_via_client(client, "admin_test", "AdminPass123")
    client.post(f"/admin/users/{student['user_id']}/status", data={"is_active": "1"})
    client.post("/logout")

    # Student đăng nhập lần đầu -> bắt buộc đổi mật khẩu
    first_login = _login_via_client(client, "sv001", "InitPass123")
    assert first_login.status_code == 302
    assert "/change-password" in first_login.headers["Location"]

    # Chưa đổi mật khẩu thì bị chặn truy cập dashboard và notifications
    assert "/change-password" in client.get("/dashboard").headers["Location"]
    assert "/change-password" in client.get("/notifications").headers["Location"]

    # Đổi mật khẩu sai mật khẩu cũ -> lỗi
    bad_change = client.post(
        "/change-password",
        data={
            "old_password": "WrongOld123",
            "new_password": "NewStudentPass123",
            "confirm_password": "NewStudentPass123",
        },
    )
    assert bad_change.status_code == 400

    # Đổi mật khẩu hợp lệ -> thành công
    good_change = client.post(
        "/change-password",
        data={
            "old_password": "InitPass123",
            "new_password": "NewStudentPass123",
            "confirm_password": "NewStudentPass123",
        },
        follow_redirects=False,
    )
    assert good_change.status_code == 302
    assert "/dashboard" in good_change.headers["Location"]

    # Student truy cập trang Admin -> 403 Forbidden
    assert client.get("/admin/users").status_code == 403
    assert client.post("/admin/users/create", data={}).status_code == 403
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
    req_resp = client.post(
        "/forgot-password",
        data={"email": "sv.otp@example.com"},
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
    wrong_otp_resp = client.post(
        "/verify-otp",
        data={"email": "sv.otp@example.com", "otp": "000000"},
    )
    assert wrong_otp_resp.status_code == 400
    assert real_otp.encode("utf-8") not in wrong_otp_resp.data

    # Nhập đúng OTP -> cho phép sang /reset-password
    ok_otp_resp = client.post(
        "/verify-otp",
        data={"email": "sv.otp@example.com", "otp": real_otp},
        follow_redirects=False,
    )
    assert ok_otp_resp.status_code == 302
    assert "/reset-password" in ok_otp_resp.headers["Location"]

    # Đặt lại mật khẩu mới
    reset_resp = client.post(
        "/reset-password",
        data={"new_password": "ResetSuccess123", "confirm_password": "ResetSuccess123"},
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
        student2 = create_user(
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
    forbidden_read = client.post(f"/notifications/{target_notif_id}/read")
    assert forbidden_read.status_code == 403
    client.post("/logout")

    # Student 1 xem và đánh dấu đã đọc
    _login_via_client(client, "sv_notif1", "UserPass123")
    page_resp = client.get("/notifications")
    assert page_resp.status_code == 200
    assert b"SE101" in page_resp.data

    client.post(f"/notifications/{target_notif_id}/read")
    with app.app_context():
        assert get_unread_notification_count(student1["user_id"]) == 3

    client.post("/notifications/read-all")
    with app.app_context():
        assert get_unread_notification_count(student1["user_id"]) == 0


def test_activity_log_recording_and_immutability(app, client):
    with app.app_context():
        lecturer = create_user(
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
    assert client.post("/admin/activity-logs/1/edit").status_code == 403
    assert client.post("/admin/activity-logs/1/delete").status_code == 403
    client.post("/logout")

    # Admin xem được log
    _login_via_client(client, "admin_test", "AdminPass123")
    logs_resp = client.get("/admin/activity-logs")
    assert logs_resp.status_code == 200
    assert b"gv_log_test" in logs_resp.data

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
