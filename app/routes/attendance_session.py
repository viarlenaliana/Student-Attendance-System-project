from flask import Blueprint, request, jsonify

from app.models.attendance_session import (
    get_attendance_session,
    get_attendance_session_list,
    create_attendance_session,
    start_attendance_session,
    end_attendance_session,
    reopen_attendance_session,
    set_attendance_method,
    get_session_method,
    refresh_qr_code,
    set_attendance_password,
    verify_session_qr,
    verify_session_password
)

attendance_session_bp = Blueprint(
    "attendance_session",
    __name__,
    url_prefix="/attendance-sessions"
)


@attendance_session_bp.route("/", methods=["GET"])
def session_list_page():
    sessions = get_attendance_session_list()
    return jsonify(sessions)


@attendance_session_bp.route("/create", methods=["POST"])
def session_create_action():
    data = request.get_json(silent=True) or {}

    session = create_attendance_session(
        data.get("schedule_id"),
        data.get("lecturer_id"),
        data.get("method")
    )

    if not session:
        return jsonify({"error": "Invalid session data"}), 400

    return jsonify(session), 201


@attendance_session_bp.route(
    "/<session_id>/start",
    methods=["POST"]
)
def session_start_action(session_id):
    result = start_attendance_session(session_id)

    if not result:
        return jsonify({"error": "Cannot start session"}), 400

    return jsonify({"message": "Session started successfully"})


@attendance_session_bp.route(
    "/<session_id>/end",
    methods=["POST"]
)
def session_end_action(session_id):
    result = end_attendance_session(session_id)

    if not result:
        return jsonify({"error": "Cannot end session"}), 400

    return jsonify({"message": "Session ended successfully"})


@attendance_session_bp.route(
    "/<session_id>/reopen",
    methods=["POST"]
)
def session_reopen_action(session_id):
    session = reopen_attendance_session(session_id)

    if not session:
        return jsonify({"error": "Cannot reopen session"}), 400

    return jsonify(session), 201


@attendance_session_bp.route(
    "/<session_id>/method",
    methods=["PUT"]
)
def session_method_action(session_id):
    data = request.get_json(silent=True) or {}

    result = set_attendance_method(
        session_id,
        data.get("method")
    )

    if not result:
        return jsonify({"error": "Invalid method"}), 400

    return jsonify({"message": "Method updated successfully"})


@attendance_session_bp.route(
    "/<session_id>/qr/refresh",
    methods=["POST"]
)
def qr_refresh_action(session_id):
    token = refresh_qr_code(session_id)

    if not token:
        return jsonify({"error": "Cannot refresh QR"}), 400

    return jsonify({"qr_token": token})


@attendance_session_bp.route(
    "/<session_id>/password",
    methods=["PUT"]
)
def session_password_action(session_id):
    data = request.get_json(silent=True) or {}

    result = set_attendance_password(
        session_id,
        data.get("password")
    )

    if not result:
        return jsonify({"error": "Cannot set password"}), 400

    return jsonify({"message": "Password set successfully"})


@attendance_session_bp.route(
    "/<session_id>",
    methods=["GET"]
)
def session_detail_action(session_id):
    session = get_attendance_session(session_id)

    if not session:
        return jsonify({"error": "Session not found"}), 404

    return jsonify(session)


@attendance_session_bp.route(
    "/<session_id>/verify-qr",
    methods=["POST"]
)
def session_verify_qr_action(session_id):
    data = request.get_json(silent=True) or {}

    result = verify_session_qr(
        session_id,
        data.get("qr_token")
    )

    return jsonify({"valid": result})


@attendance_session_bp.route(
    "/<session_id>/verify-password",
    methods=["POST"]
)
def session_verify_password_action(session_id):
    data = request.get_json(silent=True) or {}

    result = verify_session_password(
        session_id,
        data.get("password")
    )

    return jsonify({"valid": result})
