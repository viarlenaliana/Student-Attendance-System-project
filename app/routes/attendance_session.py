from flask import Blueprint, request, jsonify, render_template

from app.models.attendance_session import (
    METHODS,
    get_attendance_session,
    get_attendance_session_list,
    create_attendance_session,
    start_attendance_session,
    end_attendance_session,
    reopen_attendance_session,
    set_attendance_method,
    generate_qr_code,
    refresh_qr_code,
    verify_qr_code,
    set_attendance_password,
    verify_attendance_password,
    get_session_method
)

attendance_session_bp = Blueprint(
    "attendance_session",
    __name__,
    url_prefix="/attendance-sessions"
)


# ==============================
# LECTURER
# ==============================

@attendance_session_bp.route("/")
def session_list_page():
    sessions = get_attendance_session_list()
    return render_template(
        "lecturer/attendance_sessions/session_list.html",
        sessions=sessions,
        methods=METHODS
    )


@attendance_session_bp.route("/create", methods=["POST"])
def session_create_action():
    data = request.get_json(silent=True) or request.form

    schedule_id = data.get("schedule_id")
    lecturer_id = data.get("lecturer_id")
    method = data.get("method")

    if not schedule_id or not lecturer_id or not method:
        return jsonify({
            "success": False,
            "message": "Vui lòng nhập đầy đủ thông tin."
        }), 400

    try:
        session_id = create_attendance_session(
            schedule_id,
            lecturer_id,
            method
        )

        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": "Tạo phiên điểm danh thành công."
        })

    except ValueError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400


@attendance_session_bp.route("/<int:session_id>/start", methods=["POST"])
def session_start_action(session_id):
    success = start_attendance_session(session_id)

    return jsonify({
        "success": success,
        "message": "Đã mở phiên." if success else "Không thể mở phiên."
    })


@attendance_session_bp.route("/<int:session_id>/end", methods=["POST"])
def session_end_action(session_id):
    success = end_attendance_session(session_id)

    return jsonify({
        "success": success,
        "message": "Đã kết thúc phiên." if success else "Không thể kết thúc phiên."
    })


@attendance_session_bp.route("/<int:session_id>/reopen", methods=["POST"])
def session_reopen_action(session_id):
    try:
        new_session_id = reopen_attendance_session(session_id)

        return jsonify({
            "success": True,
            "session_id": new_session_id,
            "message": "Đã tạo phiên mới."
        })

    except ValueError as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 400


@attendance_session_bp.route("/<int:session_id>/method", methods=["POST"])
def session_method_action(session_id):
    data = request.get_json(silent=True) or request.form
    method = data.get("method")

    success = set_attendance_method(session_id, method)

    return jsonify({
        "success": success,
        "message": "Đã cập nhật phương thức." if success else "Không thể cập nhật phương thức."
    })


# ==============================
# QR
# ==============================

@attendance_session_bp.route("/<int:session_id>/qr", methods=["POST"])
def qr_refresh_action(session_id):
    token = refresh_qr_code(session_id)

    if not token:
        return jsonify({
            "success": False,
            "message": "Không thể tạo QR cho phiên này."
        }), 400

    return jsonify({
        "success": True,
        "session_id": session_id,
        "token": token
    })


@attendance_session_bp.route("/<int:session_id>/verify-qr", methods=["POST"])
def submit_qr_attendance(session_id):
    data = request.get_json(silent=True) or {}
    token = data.get("token")

    success = verify_qr_code(session_id, token)

    return jsonify({
        "success": success,
        "message": "QR hợp lệ." if success else "QR không hợp lệ hoặc đã hết hạn."
    })


# ==============================
# PASSWORD
# ==============================

@attendance_session_bp.route("/<int:session_id>/password", methods=["POST"])
def session_password_action(session_id):
    data = request.get_json(silent=True) or request.form

    password = data.get("password")

    success = set_attendance_password(session_id, password)

    return jsonify({
        "success": success,
        "message": "Đã thiết lập mật khẩu." if success else "Không thể đặt mật khẩu."
    })


@attendance_session_bp.route("/<int:session_id>/verify-password", methods=["POST"])
def submit_password_attendance(session_id):
    data = request.get_json(silent=True) or {}
    password = data.get("password")

    success = verify_attendance_password(session_id, password)

    return jsonify({
        "success": success,
        "message": "Mật khẩu đúng." if success else "Mật khẩu sai."
    })


# ==============================
# SESSION DETAIL
# ==============================

@attendance_session_bp.route("/<int:session_id>")
def session_detail_page(session_id):
    session = get_attendance_session(session_id)

    if not session:
        return "Không tìm thấy phiên điểm danh", 404

    return render_template(
        "lecturer/attendance_sessions/session_detail.html",
        session=session,
        methods=METHODS
    )


# ==============================
# STUDENT PAGE
# ==============================

@attendance_session_bp.route("/<int:session_id>/student")
def student_attendance_page(session_id):
    session = get_attendance_session(session_id)

    if not session:
        return "Không tìm thấy phiên điểm danh", 404

    return render_template(
        "student/attendance/attendance_page.html",
        session=session,
        method=get_session_method(session_id)
    )
