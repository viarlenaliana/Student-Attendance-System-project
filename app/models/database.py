"""Quản lý kết nối cơ sở dữ liệu (MySQL theo cấu hình nhóm hoặc SQLite khi cấu hình DATABASE_TYPE=sqlite).

Khởi tạo các bảng thuộc luồng tài khoản, OTP, thông báo và nhật ký hoạt động.
Khi DATABASE_TYPE=mysql nhưng kết nối thất bại, hệ thống báo lỗi rõ ràng và không tự chuyển sang SQLite.
"""
import logging
import os
import sqlite3
from datetime import datetime

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None


class database_error(Exception):
    """Lỗi thao tác cơ sở dữ liệu với thông điệp an toàn cho người dùng."""


SCHEMA_SQL_MYSQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(150) NOT NULL,
        email VARCHAR(191) NOT NULL UNIQUE,
        role VARCHAR(20) NOT NULL,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        must_change_password TINYINT(1) NOT NULL DEFAULT 1,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS password_otps (
        otp_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        email VARCHAR(191) NOT NULL,
        otp_hash VARCHAR(255) NOT NULL,
        expires_at VARCHAR(30) NOT NULL,
        is_verified TINYINT(1) NOT NULL DEFAULT 0,
        is_used TINYINT(1) NOT NULL DEFAULT 0,
        failed_attempts INT NOT NULL DEFAULT 0,
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_password_otps_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        notification_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        message TEXT NOT NULL,
        notification_type VARCHAR(50) NOT NULL DEFAULT 'system',
        related_id INT NULL,
        is_read TINYINT(1) NOT NULL DEFAULT 0,
        email_status VARCHAR(30) NOT NULL DEFAULT 'pending',
        status VARCHAR(20) NOT NULL DEFAULT 'unread',
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_logs (
        log_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NULL,
        username VARCHAR(100) NULL,
        action VARCHAR(100) NOT NULL,
        object_type VARCHAR(50) NOT NULL,
        object_id VARCHAR(50) NULL,
        result VARCHAR(20) NOT NULL,
        details TEXT NULL,
        ip_address VARCHAR(45) NULL,
        created_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_activity_logs_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

SCHEMA_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_otps (
    otp_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    is_used INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    notification_type TEXT NOT NULL DEFAULT 'system',
    related_id INTEGER NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    email_status TEXT NOT NULL DEFAULT 'pending',
    status TEXT NOT NULL DEFAULT 'unread',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
    username TEXT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NULL,
    result TEXT NOT NULL,
    details TEXT NULL,
    ip_address TEXT NULL,
    created_at TEXT NOT NULL
);
"""


def now_text():
    """Trả về thời gian hiện tại theo định dạng YYYY-MM-DD HH:MM:SS."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db_type():
    """Xác định loại cơ sở dữ liệu được cấu hình: 'mysql' hoặc 'sqlite'."""
    database_type = None
    if has_app_context():
        if current_app.config.get("DATABASE_TYPE"):
            database_type = str(current_app.config["DATABASE_TYPE"]).strip().lower()
        elif current_app.config.get("DB_TYPE"):
            database_type = str(current_app.config["DB_TYPE"]).strip().lower()
        elif current_app.config.get("SQLITE_DB_PATH") and not current_app.config.get("MYSQL_HOST"):
            database_type = "sqlite"
    if database_type is None:
        if os.environ.get("DATABASE_TYPE"):
            database_type = os.environ["DATABASE_TYPE"].strip().lower()
        elif os.environ.get("DB_TYPE"):
            database_type = os.environ["DB_TYPE"].strip().lower()
        else:
            database_type = "mysql" if pymysql is not None else "sqlite"

    if database_type not in ("mysql", "sqlite"):
        raise database_error(
            f"Cấu hình DATABASE_TYPE='{database_type}' không hợp lệ. Chỉ hỗ trợ 'mysql' hoặc 'sqlite'."
        )
    return database_type


def get_sqlite_connection():
    """Tạo kết nối SQLite khi cấu hình DATABASE_TYPE=sqlite."""
    if has_app_context() and current_app.config.get("SQLITE_DB_PATH"):
        database_path = current_app.config["SQLITE_DB_PATH"]
    elif has_app_context() and current_app.config.get("database_path"):
        database_path = current_app.config["database_path"]
    else:
        database_path = os.environ.get("SQLITE_DB_PATH", "demo.db")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db_connection():
    """Lấy kết nối cơ sở dữ liệu theo đúng DATABASE_TYPE đã cấu hình (không tự fallback khi MySQL lỗi)."""
    database_type = get_db_type()
    if database_type == "mysql":
        if pymysql is None:
            raise database_error(
                "Đã cấu hình DATABASE_TYPE=mysql nhưng chưa cài đặt thư viện PyMySQL."
            )
        config = current_app.config if has_app_context() else {}
        host = config.get("MYSQL_HOST", os.environ.get("MYSQL_HOST", "localhost"))
        user = config.get("MYSQL_USER", os.environ.get("MYSQL_USER", "root"))
        password = config.get("MYSQL_PASSWORD", os.environ.get("MYSQL_PASSWORD", ""))
        database_name = config.get("MYSQL_DB", os.environ.get("MYSQL_DB", "student_attendance"))
        port = int(config.get("MYSQL_PORT", os.environ.get("MYSQL_PORT", 3306)))
        charset = config.get("MYSQL_CHARSET", os.environ.get("MYSQL_CHARSET", "utf8mb4"))
        try:
            return pymysql.connect(
                host=host,
                user=user,
                password=password,
                database=database_name,
                port=port,
                charset=charset,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
            )
        except Exception as error:
            logger.error(
                "Kết nối MySQL thất bại (%s:%s/%s, user=%s): %s",
                host,
                port,
                database_name,
                user,
                error,
            )
            raise database_error(
                f"Không thể kết nối tới MySQL ({host}:{port}/{database_name}, user='{user}'). "
                f"Vui lòng kiểm tra MySQL server và cấu hình kết nối. Chi tiết: {error}"
            ) from error
    return get_sqlite_connection()


def get_connection_db_type(connection):
    """Xác định loại cơ sở dữ liệu từ đối tượng connection."""
    if pymysql and isinstance(connection, pymysql.connections.Connection):
        return "mysql"
    return "sqlite"


def adapt_sql(sql_query, database_type):
    """Chuyển đổi placeholder '?' sang '%s' khi chạy trên MySQL."""
    if database_type == "mysql":
        return sql_query.replace("?", "%s")
    return sql_query


def explain_integrity_error(error_message):
    """Chuyển lỗi ràng buộc database sang thông báo tiếng Việt thân thiện."""
    upper_message = error_message.upper()
    if "UNIQUE" in upper_message or "1062" in upper_message or "DUPLICATE ENTRY" in upper_message:
        return "Dữ liệu bị trùng với bản ghi đã tồn tại (tên đăng nhập hoặc email đã được sử dụng)."
    if "FOREIGN KEY" in upper_message or "1452" in upper_message or "1451" in upper_message:
        return "Dữ liệu liên kết không hợp lệ hoặc đang được sử dụng."
    return "Không thể lưu dữ liệu do vi phạm ràng buộc cơ sở dữ liệu."


def init_account_system_tables():
    """Khởi tạo các bảng users, password_otps, notifications và activity_logs."""
    connection = get_db_connection()
    database_type = get_connection_db_type(connection)
    try:
        if database_type == "mysql":
            with connection.cursor() as cursor:
                for statement in SCHEMA_SQL_MYSQL:
                    cleaned_statement = statement.strip()
                    if cleaned_statement:
                        cursor.execute(cleaned_statement)
            connection.commit()
        else:
            connection.executescript(SCHEMA_SQL_SQLITE)
            connection.commit()
    finally:
        connection.close()


def fetch_one(sql_query, params=()):
    """Truy vấn một bản ghi và trả về dict hoặc None."""
    connection = get_db_connection()
    database_type = get_connection_db_type(connection)
    try:
        adapted_query = adapt_sql(sql_query, database_type)
        if database_type == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(adapted_query, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        row = connection.execute(adapted_query, params).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def fetch_all(sql_query, params=()):
    """Truy vấn danh sách bản ghi và trả về list các dict."""
    connection = get_db_connection()
    database_type = get_connection_db_type(connection)
    try:
        adapted_query = adapt_sql(sql_query, database_type)
        if database_type == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(adapted_query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        rows = connection.execute(adapted_query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def run_write(sql_query, params=()):
    """Thực thi câu lệnh ghi (INSERT/UPDATE/DELETE) và trả về lastrowid."""
    connection = get_db_connection()
    database_type = get_connection_db_type(connection)
    try:
        adapted_query = adapt_sql(sql_query, database_type)
        if database_type == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(adapted_query, params)
                connection.commit()
                return cursor.lastrowid
        cursor = connection.execute(adapted_query, params)
        connection.commit()
        return cursor.lastrowid
    except Exception as error:
        try:
            connection.rollback()
        except Exception:
            pass
        raise database_error(explain_integrity_error(str(error))) from error
    finally:
        connection.close()
