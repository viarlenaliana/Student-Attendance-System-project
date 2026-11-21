import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash


# Database demo riêng của module
BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BASE_DIR / "attendance_session.db"

METHODS = [
    "QR code",
    "Password",
    "QR code combined with password",
    "Manual attendance"
]

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                lecturer_id INTEGER NOT NULL,
                method TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Scheduled',
                qr_token_hash TEXT,
                qr_expiry TEXT,
                attendance_password TEXT,
                created_at TEXT NOT NULL
            )
        """)


def get_attendance_session(session_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM attendance_sessions
            WHERE session_id = ?
            """,
            (session_id,)
        ).fetchone()

        return dict(row) if row else None


def get_attendance_session_list(filters=None):
    filters = filters or {}

    query = "SELECT * FROM attendance_sessions WHERE 1=1"
    values = []

    if filters.get("lecturer_id"):
        query += " AND lecturer_id = ?"
        values.append(filters["lecturer_id"])

    if filters.get("status"):
        query += " AND status = ?"
        values.append(filters["status"])

    query += " ORDER BY session_id DESC"

    with get_connection() as conn:
        rows = conn.execute(query, values).fetchall()
        return [dict(row) for row in rows]


def create_attendance_session(schedule_id, lecturer_id, method):
    if method not in METHODS:
        raise ValueError("Phương thức điểm danh không hợp lệ.")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO attendance_sessions (
                schedule_id,
                lecturer_id,
                method,
                status,
                created_at
            )
            VALUES (?, ?, ?, 'Scheduled', ?)
            """,
            (
                schedule_id,
                lecturer_id,
                method,
                datetime.now().isoformat()
            )
        )

        return cursor.lastrowid


def start_attendance_session(session_id):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE attendance_sessions
            SET status = 'Open'
            WHERE session_id = ?
              AND status = 'Scheduled'
            """,
            (session_id,)
        )

        return cursor.rowcount > 0


def end_attendance_session(session_id):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE attendance_sessions
            SET status = 'Ended',
                qr_token_hash = NULL,
                qr_expiry = NULL
            WHERE session_id = ?
              AND status = 'Open'
            """,
            (session_id,)
        )

        return cursor.rowcount > 0


def reopen_attendance_session(old_session_id):
    old_session = get_attendance_session(old_session_id)

    if not old_session:
        raise ValueError("Không tìm thấy phiên điểm danh.")

    return create_attendance_session(
        old_session["schedule_id"],
        old_session["lecturer_id"],
        old_session["method"]
    )


def set_attendance_method(session_id, method):
    if method not in METHODS:
        return False

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE attendance_sessions
            SET method = ?
            WHERE session_id = ?
              AND status = 'Scheduled'
            """,
            (method, session_id)
        )

        return cursor.rowcount > 0


def get_session_method(session_id):
    session = get_attendance_session(session_id)

    if session:
        return session["method"]

    return None


# ==============================
# QR CODE
# ==============================

def generate_qr_code(session_id):
    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return None

    qr_token = secrets.token_urlsafe(32)
    expiry = datetime.now() + timedelta(seconds=60)

    token_hash = hashlib.sha256(qr_token.encode()).hexdigest()

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE attendance_sessions
            SET qr_token_hash = ?,
                qr_expiry = ?
            WHERE session_id = ?
            """,
            (token_hash, expiry.isoformat(), session_id)
        )

    return qr_token


def refresh_qr_code(session_id):
    return generate_qr_code(session_id)


def verify_qr_code(session_id, qr_token):
    if not qr_token:
        return False

    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return False

    if not session["qr_token_hash"] or not session["qr_expiry"]:
        return False

    expiry = datetime.fromisoformat(session["qr_expiry"])

    if datetime.now() > expiry:
        return False

    token_hash = hashlib.sha256(qr_token.encode()).hexdigest()

    return secrets.compare_digest(
        token_hash,
        session["qr_token_hash"]
    )


# ==============================
# ATTENDANCE PASSWORD
# ==============================

def set_attendance_password(session_id, password):
    if not password or len(password) < 4:
        return False

    hashed_password = generate_password_hash(password)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE attendance_sessions
            SET attendance_password = ?
            WHERE session_id = ?
              AND status != 'Ended'
            """,
            (hashed_password, session_id)
        )

        return cursor.rowcount > 0


def verify_attendance_password(session_id, password):
    if not password:
        return False

    session = get_attendance_session(session_id)

    if not session or session["status"] != "Open":
        return False

    hashed_password = session["attendance_password"]

    if not hashed_password:
        return False

    return check_password_hash(hashed_password, password)


initialize_database()
