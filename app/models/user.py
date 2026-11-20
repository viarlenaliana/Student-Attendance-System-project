"""Quản lý tài khoản, xác thực đăng nhập, phân quyền, đổi mật khẩu và khôi phục mật khẩu qua OTP.

Tuân thủ quy ước tên hàm chuẩn và bảo mật:
- Không lưu hoặc trả mật khẩu / OTP dạng chữ thường về HTML, JavaScript hay log.
- Mọi module dùng chung get_current_user() và check_user_permission().
"""
from datetime import datetime, timedelta
import re
import secrets

from flask import current_app, has_app_context, has_request_context, session
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.database import fetch_all, fetch_one, now_text, run_write
from app.utils.email_service import send_otp_email

VALID_ROLES = ("admin", "lecturer", "student")
ADMIN_CREATABLE_ROLES = ("lecturer", "student")

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OTP_PATTERN = re.compile(r"^\d{6}$")

SAFE_USER_COLUMNS = (
    "user_id, username, full_name, email, role, is_active, "
    "must_change_password, status, created_at, updated_at"
)


class auth_error(Exception):
    """Lỗi xác thực, phân quyền hoặc dữ liệu tài khoản."""


def _get_config_int(key, default_value):
    if has_app_context() and current_app.config.get(key) is not None:
        return int(current_app.config[key])
    return int(default_value)


def _normalize_user_record(user_row):
    """Chuẩn hóa dữ liệu user trả ra ngoài, tuyệt đối loại bỏ password_hash."""
    if not user_row:
        return None
    normalized = dict(user_row)
    normalized.pop("password_hash", None)
    normalized["is_active"] = bool(normalized.get("is_active"))
    normalized["must_change_password"] = bool(normalized.get("must_change_password"))
    return normalized


def _get_user_auth_by_id(user_id):
    return fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))


def _get_user_auth_by_username(username):
    return fetch_one("SELECT * FROM users WHERE username = ?", (username,))


def _get_user_auth_by_email(email):
    return fetch_one("SELECT * FROM users WHERE email = ?", (email,))


def hash_password(password):
    """Băm mật khẩu hoặc mã OTP bằng thuật toán băm an toàn của Werkzeug."""
    if not isinstance(password, str) or not password:
        raise auth_error("Giá trị cần băm không được để trống.")
    return generate_password_hash(password)


def check_password(password, password_hash):
    """Kiểm tra mật khẩu dạng thô với chuỗi hash đã lưu."""
    if not password or not password_hash:
        return False
    return check_password_hash(password_hash, password)


def validate_username(username):
    clean_username = (username or "").strip()
    if not clean_username:
        raise auth_error("Tên đăng nhập không được để trống.")
    if not USERNAME_PATTERN.match(clean_username):
        raise auth_error("Tên đăng nhập chỉ gồm chữ, số, dấu chấm, gạch dưới hoặc gạch ngang (3–50 ký tự).")
    return clean_username


def validate_email(email):
    clean_email = (email or "").strip().lower()
    if not clean_email:
        raise auth_error("Email không được để trống.")
    if not EMAIL_PATTERN.match(clean_email):
        raise auth_error("Địa chỉ email không hợp lệ.")
    return clean_email


def validate_full_name(full_name):
    clean_name = (full_name or "").strip()
    if not clean_name:
        raise auth_error("Họ và tên không được để trống.")
    if len(clean_name) > 150:
        raise auth_error("Họ và tên tối đa 150 ký tự.")
    return clean_name


def validate_role(role, allowed_roles=VALID_ROLES):
    clean_role = (role or "").strip().lower()
    if clean_role not in allowed_roles:
        raise auth_error("Vai trò tài khoản không hợp lệ.")
    return clean_role


def validate_password_strength(password):
    """Kiểm tra độ mạnh mật khẩu theo chính sách bảo mật."""
    min_length = _get_config_int("PASSWORD_MIN_LENGTH", 8)
    if not isinstance(password, str) or not password:
        raise auth_error("Mật khẩu không được để trống.")
    if len(password) < min_length:
        raise auth_error(f"Mật khẩu phải có ít nhất {min_length} ký tự.")
    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    if not (has_upper and has_lower and has_digit):
        raise auth_error("Mật khẩu phải bao gồm ít nhất 1 chữ hoa, 1 chữ thường và 1 chữ số.")
    return password


def get_user_by_id(user_id):
    """Lấy thông tin tài khoản an toàn theo user_id (không kèm password_hash)."""
    try:
        numeric_user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    row = fetch_one(f"SELECT {SAFE_USER_COLUMNS} FROM users WHERE user_id = ?", (numeric_user_id,))
    return _normalize_user_record(row)


def get_user_by_username(username):
    """Lấy thông tin tài khoản an toàn theo username."""
    clean_username = (username or "").strip()
    if not clean_username:
        return None
    row = fetch_one(f"SELECT {SAFE_USER_COLUMNS} FROM users WHERE username = ?", (clean_username,))
    return _normalize_user_record(row)


def get_user_by_email(email):
    """Lấy thông tin tài khoản an toàn theo email."""
    clean_email = (email or "").strip().lower()
    if not clean_email:
        return None
    row = fetch_one(f"SELECT {SAFE_USER_COLUMNS} FROM users WHERE email = ?", (clean_email,))
    return _normalize_user_record(row)


def get_user_list(filters=None):
    """Truy vấn danh sách tài khoản phục vụ màn hình quản lý của Admin."""
    filters = filters or {}
    sql_query = f"SELECT {SAFE_USER_COLUMNS} FROM users WHERE 1 = 1"
    params = []

    if filters.get("role"):
        role_value = str(filters["role"]).strip().lower()
        if role_value in VALID_ROLES:
            sql_query += " AND role = ?"
            params.append(role_value)

    if filters.get("status") in ("active", "locked"):
        sql_query += " AND status = ?"
        params.append(filters["status"])
    elif filters.get("is_active") is not None and filters.get("is_active") != "":
        is_active_int = 1 if str(filters["is_active"]).lower() in ("1", "true", "active") else 0
        sql_query += " AND is_active = ?"
        params.append(is_active_int)

    if filters.get("keyword"):
        keyword = "%" + str(filters["keyword"]).strip() + "%"
        sql_query += " AND (username LIKE ? OR full_name LIKE ? OR email LIKE ?)"
        params.extend([keyword, keyword, keyword])

    sql_query += " ORDER BY user_id DESC"
    return [_normalize_user_record(row) for row in fetch_all(sql_query, tuple(params))]


def login_user(username, password):
    """Xác thực thông tin đăng nhập và khởi tạo phiên đăng nhập theo vai trò."""
    clean_username = (username or "").strip()
    if not clean_username or not password:
        raise auth_error("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")

    user_auth = _get_user_auth_by_username(clean_username)
    if user_auth is None or not check_password(password, user_auth["password_hash"]):
        raise auth_error("Tên đăng nhập hoặc mật khẩu không chính xác.")

    if not user_auth["is_active"]:
        raise auth_error("Tài khoản của bạn đang bị khóa. Vui lòng liên hệ quản trị viên.")

    if has_request_context():
        session.clear()
        session["user_id"] = user_auth["user_id"]
        session["role"] = user_auth["role"]
        session.permanent = True

    return _normalize_user_record(user_auth)


def logout_user():
    """Kết thúc phiên đăng nhập hiện tại."""
    if has_request_context():
        session.clear()
    return True


def get_current_user():
    """Hàm dùng chung trả về user đang đăng nhập hoặc None."""
    if not has_request_context():
        return None
    session_user_id = session.get("user_id")
    if not session_user_id:
        return None

    user = get_user_by_id(session_user_id)
    if user is None or not user["is_active"]:
        session.clear()
        return None
    return user


def check_user_permission(user_id, role, resource_id=None):
    """Kiểm tra người dùng có đang hoạt động và có quyền phù hợp với vai trò/tài nguyên hay không."""
    user = get_user_by_id(user_id)
    if user is None or not user["is_active"]:
        return False

    if isinstance(role, (list, tuple, set)):
        allowed_roles = {str(item).strip().lower() for item in role}
    else:
        allowed_roles = {str(role).strip().lower()}

    if user["role"] not in allowed_roles:
        return False

    if resource_id is not None and isinstance(resource_id, dict):
        owner_user_id = resource_id.get("owner_user_id")
        if owner_user_id is not None and user["role"] != "admin":
            return int(owner_user_id) == int(user["user_id"])

    return True


def create_user(user_data, allowed_roles=VALID_ROLES):
    """Tạo tài khoản mới (chỉ Admin thực hiện; không dùng cho tự đăng ký)."""
    user_data = user_data or {}
    clean_username = validate_username(user_data.get("username"))
    clean_full_name = validate_full_name(user_data.get("full_name"))
    clean_email = validate_email(user_data.get("email"))
    clean_role = validate_role(user_data.get("role"), allowed_roles=allowed_roles)
    raw_password = validate_password_strength(user_data.get("password"))

    if get_user_by_username(clean_username) is not None:
        raise auth_error("Tên đăng nhập đã tồn tại trong hệ thống.")
    if get_user_by_email(clean_email) is not None:
        raise auth_error("Địa chỉ email đã được sử dụng cho tài khoản khác.")

    is_active_flag = 1 if user_data.get("is_active", True) else 0
    status_text = "active" if is_active_flag else "locked"
    must_change_flag = 1 if user_data.get("must_change_password", True) else 0
    password_hash = hash_password(raw_password)
    timestamp_text = now_text()

    user_id = run_write(
        """
        INSERT INTO users (
            username, password_hash, full_name, email, role,
            is_active, must_change_password, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_username,
            password_hash,
            clean_full_name,
            clean_email,
            clean_role,
            is_active_flag,
            must_change_flag,
            status_text,
            timestamp_text,
            timestamp_text,
        ),
    )
    return get_user_by_id(user_id)


def update_user(user_id, user_data, allowed_roles=VALID_ROLES):
    """Cập nhật thông tin tài khoản (họ tên, email, vai trò hoặc đặt lại mật khẩu khởi tạo)."""
    existing_user = get_user_by_id(user_id)
    if existing_user is None:
        raise auth_error("Không tìm thấy tài khoản cần cập nhật.")

    user_data = user_data or {}
    updates = {}

    if "full_name" in user_data and user_data["full_name"] is not None:
        updates["full_name"] = validate_full_name(user_data["full_name"])

    if "email" in user_data and user_data["email"] is not None:
        clean_email = validate_email(user_data["email"])
        conflict_user = get_user_by_email(clean_email)
        if conflict_user is not None and int(conflict_user["user_id"]) != int(user_id):
            raise auth_error("Email đã được sử dụng bởi tài khoản khác.")
        updates["email"] = clean_email

    if "role" in user_data and user_data["role"] is not None:
        updates["role"] = validate_role(user_data["role"], allowed_roles=allowed_roles)

    if user_data.get("password"):
        new_password = validate_password_strength(user_data["password"])
        updates["password_hash"] = hash_password(new_password)
        updates["must_change_password"] = 1

    if "is_active" in user_data and user_data["is_active"] is not None:
        is_active_flag = 1 if bool(user_data["is_active"]) else 0
        updates["is_active"] = is_active_flag
        updates["status"] = "active" if is_active_flag else "locked"

    if not updates:
        raise auth_error("Không có thông tin hợp lệ để cập nhật.")

    updates["updated_at"] = now_text()
    assignments = ", ".join(f"{column_name} = ?" for column_name in updates)
    run_write(
        f"UPDATE users SET {assignments} WHERE user_id = ?",
        tuple(updates.values()) + (user_id,),
    )
    return get_user_by_id(user_id)


def set_user_status(user_id, is_active):
    """Khóa (is_active=False) hoặc mở khóa (is_active=True) tài khoản người dùng."""
    existing_user = get_user_by_id(user_id)
    if existing_user is None:
        raise auth_error("Không tìm thấy tài khoản.")

    is_active_flag = 1 if bool(is_active) else 0
    status_text = "active" if is_active_flag else "locked"
    run_write(
        "UPDATE users SET is_active = ?, status = ?, updated_at = ? WHERE user_id = ?",
        (is_active_flag, status_text, now_text(), user_id),
    )
    return True


def change_password(user_id, old_password, new_password):
    """Đổi mật khẩu cho người dùng sau khi kiểm tra mật khẩu hiện tại và mật khẩu mới."""
    user_auth = _get_user_auth_by_id(user_id)
    if user_auth is None:
        raise auth_error("Không tìm thấy tài khoản.")
    if not user_auth["is_active"]:
        raise auth_error("Tài khoản đang bị khóa, không thể đổi mật khẩu.")
    if not old_password:
        raise auth_error("Vui lòng nhập mật khẩu hiện tại.")
    if not check_password(old_password, user_auth["password_hash"]):
        raise auth_error("Mật khẩu hiện tại không chính xác.")

    validate_password_strength(new_password)
    if new_password == old_password:
        raise auth_error("Mật khẩu mới phải khác mật khẩu hiện tại.")

    new_password_hash = hash_password(new_password)
    run_write(
        "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE user_id = ?",
        (new_password_hash, now_text(), user_id),
    )
    return True


def _get_latest_active_otp_record(email):
    """Tìm bản ghi OTP chưa sử dụng mới nhất cho email."""
    return fetch_one(
        """
        SELECT * FROM password_otps
        WHERE email = ? AND is_used = 0
        ORDER BY otp_id DESC
        LIMIT 1
        """,
        (email,),
    )


def _is_otp_expired(expires_at_text):
    try:
        expires_at = datetime.strptime(expires_at_text, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    return datetime.now() > expires_at


def create_password_otp(email):
    """Tạo mã OTP ngẫu nhiên, lưu dạng băm và gửi qua email đã đăng ký (không trả OTP ra giao diện)."""
    clean_email = validate_email(email)
    user_auth = _get_user_auth_by_email(clean_email)
    if user_auth is None:
        raise auth_error("Email chưa được đăng ký trong hệ thống.")
    if not user_auth["is_active"]:
        raise auth_error("Tài khoản gắn với email này đang bị khóa.")

    expiry_minutes = _get_config_int("OTP_EXPIRY_MINUTES", 10)
    cooldown_seconds = _get_config_int("OTP_RESEND_COOLDOWN_SECONDS", 60)

    latest_record = _get_latest_active_otp_record(clean_email)
    if latest_record and cooldown_seconds > 0 and not _is_otp_expired(latest_record["expires_at"]):
        try:
            created_at = datetime.strptime(latest_record["created_at"], "%Y-%m-%d %H:%M:%S")
            elapsed_seconds = (datetime.now() - created_at).total_seconds()
            if elapsed_seconds < cooldown_seconds:
                remaining_seconds = max(1, int(cooldown_seconds - elapsed_seconds))
                raise auth_error(f"Vui lòng chờ {remaining_seconds} giây trước khi yêu cầu mã OTP mới.")
        except ValueError:
            pass

    timestamp_text = now_text()
    run_write(
        "UPDATE password_otps SET is_used = 1, updated_at = ? WHERE user_id = ? AND is_used = 0",
        (timestamp_text, user_auth["user_id"]),
    )

    otp_code = f"{secrets.randbelow(1000000):06d}"
    otp_hash = hash_password(otp_code)
    expires_at = (datetime.now() + timedelta(minutes=expiry_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    run_write(
        """
        INSERT INTO password_otps (
            user_id, email, otp_hash, expires_at,
            is_verified, is_used, failed_attempts, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?)
        """,
        (
            user_auth["user_id"],
            clean_email,
            otp_hash,
            expires_at,
            timestamp_text,
            timestamp_text,
        ),
    )

    delivery = send_otp_email(clean_email, user_auth["full_name"], otp_code, expiry_minutes)
    return {
        "sent": True,
        "email": clean_email,
        "email_status": delivery.get("status", "skipped"),
        "expiry_minutes": expiry_minutes,
    }


def verify_password_otp(email, otp):
    """Xác minh mã OTP gửi qua email. Trả về True nếu hợp lệ, False nếu sai/hết hạn."""
    try:
        clean_email = validate_email(email)
    except auth_error:
        return False

    clean_otp = (otp or "").strip()
    if not OTP_PATTERN.match(clean_otp):
        return False

    user_auth = _get_user_auth_by_email(clean_email)
    if user_auth is None or not user_auth["is_active"]:
        return False

    otp_record = _get_latest_active_otp_record(clean_email)
    if otp_record is None:
        return False

    max_attempts = _get_config_int("OTP_MAX_ATTEMPTS", 5)
    if _is_otp_expired(otp_record["expires_at"]) or int(otp_record["failed_attempts"]) >= max_attempts:
        run_write(
            "UPDATE password_otps SET is_used = 1, updated_at = ? WHERE otp_id = ?",
            (now_text(), otp_record["otp_id"]),
        )
        return False

    if check_password(clean_otp, otp_record["otp_hash"]):
        run_write(
            "UPDATE password_otps SET is_verified = 1, updated_at = ? WHERE otp_id = ?",
            (now_text(), otp_record["otp_id"]),
        )
        return True

    new_attempts = int(otp_record["failed_attempts"]) + 1
    invalidate_flag = 1 if new_attempts >= max_attempts else 0
    run_write(
        "UPDATE password_otps SET failed_attempts = ?, is_used = ?, updated_at = ? WHERE otp_id = ?",
        (new_attempts, invalidate_flag, now_text(), otp_record["otp_id"]),
    )
    return False


def reset_password(email, otp, new_password):
    """Đặt lại mật khẩu mới sau khi OTP được xác minh thành công."""
    clean_email = validate_email(email)
    clean_otp = (otp or "").strip()
    if not OTP_PATTERN.match(clean_otp):
        raise auth_error("Mã OTP phải gồm đúng 6 chữ số.")

    validate_password_strength(new_password)

    user_auth = _get_user_auth_by_email(clean_email)
    if user_auth is None:
        raise auth_error("Không tìm thấy tài khoản gắn với email này.")
    if not user_auth["is_active"]:
        raise auth_error("Tài khoản đang bị khóa, không thể đặt lại mật khẩu.")

    otp_record = _get_latest_active_otp_record(clean_email)
    if otp_record is None or _is_otp_expired(otp_record["expires_at"]):
        raise auth_error("Mã OTP không tồn tại hoặc đã hết hạn. Vui lòng yêu cầu mã mới.")

    max_attempts = _get_config_int("OTP_MAX_ATTEMPTS", 5)
    if int(otp_record["failed_attempts"]) >= max_attempts:
        run_write(
            "UPDATE password_otps SET is_used = 1, updated_at = ? WHERE otp_id = ?",
            (now_text(), otp_record["otp_id"]),
        )
        raise auth_error("Mã OTP đã bị vô hiệu hóa do nhập sai quá số lần cho phép.")

    if not check_password(clean_otp, otp_record["otp_hash"]):
        new_attempts = int(otp_record["failed_attempts"]) + 1
        invalidate_flag = 1 if new_attempts >= max_attempts else 0
        run_write(
            "UPDATE password_otps SET failed_attempts = ?, is_used = ?, updated_at = ? WHERE otp_id = ?",
            (new_attempts, invalidate_flag, now_text(), otp_record["otp_id"]),
        )
        raise auth_error("Mã OTP không chính xác.")

    if not otp_record["is_verified"]:
        raise auth_error("Mã OTP chưa được xác minh thành công. Vui lòng xác minh OTP trước khi đổi mật khẩu.")

    timestamp_text = now_text()
    new_password_hash = hash_password(new_password)
    run_write(
        "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE user_id = ?",
        (new_password_hash, timestamp_text, user_auth["user_id"]),
    )
    run_write(
        "UPDATE password_otps SET is_used = 1, updated_at = ? WHERE otp_id = ?",
        (timestamp_text, otp_record["otp_id"]),
    )
    return True


def get_verified_otp_record(email):
    """Kiểm tra email có bản ghi OTP đã xác minh hợp lệ và còn hạn hay không."""
    try:
        clean_email = validate_email(email)
    except auth_error:
        return None
    otp_record = _get_latest_active_otp_record(clean_email)
    if otp_record is None or not otp_record["is_verified"]:
        return None
    if _is_otp_expired(otp_record["expires_at"]):
        return None
    return otp_record


def complete_verified_password_reset(email, otp_id, new_password):
    """Hoàn tất đặt lại mật khẩu cho phiên đã xác minh OTP thành công (không lưu OTP vào session)."""
    clean_email = validate_email(email)
    validate_password_strength(new_password)

    user_auth = _get_user_auth_by_email(clean_email)
    if user_auth is None:
        raise auth_error("Không tìm thấy tài khoản gắn với email này.")
    if not user_auth["is_active"]:
        raise auth_error("Tài khoản đang bị khóa, không thể đặt lại mật khẩu.")

    otp_record = fetch_one(
        "SELECT * FROM password_otps WHERE otp_id = ? AND email = ? AND is_used = 0",
        (otp_id, clean_email),
    )
    if otp_record is None or not otp_record["is_verified"] or _is_otp_expired(otp_record["expires_at"]):
        raise auth_error("Phiên xác minh OTP không hợp lệ hoặc đã hết hạn. Vui lòng thực hiện lại.")

    timestamp_text = now_text()
    new_password_hash = hash_password(new_password)
    run_write(
        "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE user_id = ?",
        (new_password_hash, timestamp_text, user_auth["user_id"]),
    )
    run_write(
        "UPDATE password_otps SET is_used = 1, updated_at = ? WHERE otp_id = ?",
        (timestamp_text, otp_record["otp_id"]),
    )
    return True


def seed_admin_from_env():
    """Khởi tạo tài khoản Admin từ biến môi trường nếu hệ thống chưa có Admin nào."""
    import os

    existing_admin = fetch_one("SELECT user_id FROM users WHERE role = 'admin' LIMIT 1")
    if existing_admin is not None:
        return None

    admin_username = os.environ.get("INIT_ADMIN_USERNAME", "").strip()
    admin_email = os.environ.get("INIT_ADMIN_EMAIL", "").strip()
    admin_password = os.environ.get("INIT_ADMIN_PASSWORD", "")
    admin_full_name = os.environ.get("INIT_ADMIN_FULL_NAME", "System Administrator").strip()

    if not (admin_username and admin_email and admin_password):
        return None

    return create_user(
        {
            "username": admin_username,
            "full_name": admin_full_name,
            "email": admin_email,
            "role": "admin",
            "password": admin_password,
            "must_change_password": False,
        }
    )
