
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash


attendance_methods = [
    "QR code",
    "Password",
    "QR code combined with password",
    "Manual attendance"
]

# Prototype: data is stored temporarily in memory
attendance_sessions = {}


def check_attendance_method(method):
    return method in attendance_methods


def generate_qr_token():
    return secrets.token_urlsafe(32)


def hash_attendance_password(password):
    if not password:
        return None

    return generate_password_hash(password)


def verify_attendance_password(password, password_hash):
    if not password or not password_hash:
        return False

    return check_password_hash(password_hash, password)


def verify_qr_code(qr_token, stored_token):
    if not qr_token or not stored_token:
        return False

    return secrets.compare_digest(qr_token, stored_token)


def get_attendance_session(session_id):
    return attendance_sessions.get(session_id)


def get_attendance_session_list(filters=None):
    sessions = list(attendance_sessions.values())

    if filters:
        for key, value in filters.items():
            sessions = [
                session for session in sessions
                if session.get(key) == value
            ]

    return sessions


def create_attendance_session(schedule_id, lecturer_id, method):
    if not schedule_id or not lecturer_id:
        return None

    if not check_attendance_method(method):
        return None

    session_id = secrets.token_urlsafe(12)

    session = {
        "session_id": session_id,
        "schedule_id": schedule_id,
        "lecturer_id": lecturer_id,
        "method": method,
        "status": "Scheduled",
        "qr_token": None,
        "qr_expiry": None,
        "password_hash": None,
        "created_at": datetime.now(),
        "started_at": None,
        "ended_at": None
    }

    attendance_sessions[session_id] = session

    return session


def start_attendance_session(session_id):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Scheduled":
        return False

    session["status"] = "Open"
    session["started_at"] = datetime.now()

    if session["method"] in [
        "QR code",
        "QR code combined with password"
    ]:
        refresh_qr_code(session_id)

    return True


def end_attendance_session(session_id):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return False

    session["status"] = "Ended"
    session["ended_at"] = datetime.now()

    session["qr_token"] = None
    session["qr_expiry"] = None

    return True


def reopen_attendance_session(old_session_id):
    old_session = get_attendance_session(old_session_id)

    if not old_session or old_session["status"] != "Ended":
        return None

    # Create a new session without overwriting the old one
    new_session = create_attendance_session(
        old_session["schedule_id"],
        old_session["lecturer_id"],
        old_session["method"]
    )

    return new_session


def set_attendance_method(session_id, method):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Scheduled":
        return False

    if not check_attendance_method(method):
        return False

    session["method"] = method
    session["qr_token"] = None
    session["qr_expiry"] = None
    session["password_hash"] = None

    return True


def get_session_method(session_id):
    session = get_attendance_session(session_id)

    if not session:
        return None

    return session["method"]


def refresh_qr_code(session_id, expiry_minutes=1):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return None

    if session["method"] not in [
        "QR code",
        "QR code combined with password"
    ]:
        return None

    session["qr_token"] = generate_qr_token()
    session["qr_expiry"] = datetime.now() + timedelta(
        minutes=expiry_minutes
    )

    return session["qr_token"]


def verify_session_qr(session_id, qr_token):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return False

    if not session["qr_token"] or not session["qr_expiry"]:
        return False

    if datetime.now() > session["qr_expiry"]:
        return False

    return verify_qr_code(qr_token, session["qr_token"])


def set_attendance_password(session_id, password):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Scheduled":
        return False

    if session["method"] not in [
        "Password",
        "QR code combined with password"
    ]:
        return False

    if not password or len(password) < 4:
        return False

    session["password_hash"] = hash_attendance_password(password)

    return True


def verify_session_password(session_id, password):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return False

    if session["method"] not in [
        "Password",
        "QR code combined with password"
    ]:
        return False

    return verify_attendance_password(
        password,
        session["password_hash"]
    )
