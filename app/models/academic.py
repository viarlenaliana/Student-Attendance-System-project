"""Dữ liệu học tập: khoa/phòng ban, môn học, lớp học phần, đăng ký học.

Quản lý kết nối cơ sở dữ liệu chung (MySQL và SQLite dự phòng)
cùng schema dùng chung cho student, lecturer, schedule.
"""
import os
import re
import sqlite3
from datetime import datetime

from flask import current_app, has_app_context

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None


class academic_error(Exception):
    """Lỗi dữ liệu/nghiệp vụ; message hiển thị được cho người dùng."""


# Schema MySQL chuẩn theo quy ước nhóm
SCHEMA_SQL_MYSQL = [
    """
    CREATE TABLE IF NOT EXISTS departments (
        department_id INT AUTO_INCREMENT PRIMARY KEY,
        department_name VARCHAR(191) NOT NULL UNIQUE,
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS students (
        student_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNIQUE,
        full_name VARCHAR(150) NOT NULL,
        email VARCHAR(191) NOT NULL UNIQUE,
        department_id INT,
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_students_dept FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS lecturers (
        lecturer_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNIQUE,
        full_name VARCHAR(150) NOT NULL,
        email VARCHAR(191) NOT NULL UNIQUE,
        department_id INT,
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_lecturers_dept FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS courses (
        course_id INT AUTO_INCREMENT PRIMARY KEY,
        course_name VARCHAR(191) NOT NULL UNIQUE,
        department_id INT,
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_courses_dept FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS classes (
        class_id INT AUTO_INCREMENT PRIMARY KEY,
        class_name VARCHAR(100) NOT NULL UNIQUE,
        course_id INT NOT NULL,
        lecturer_id INT,
        semester VARCHAR(50),
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_classes_course FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE RESTRICT,
        CONSTRAINT fk_classes_lecturer FOREIGN KEY (lecturer_id) REFERENCES lecturers(lecturer_id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS enrollments (
        enrollment_id INT AUTO_INCREMENT PRIMARY KEY,
        class_id INT NOT NULL,
        student_id INT NOT NULL,
        created_at VARCHAR(30) NOT NULL,
        UNIQUE KEY uq_class_student (class_id, student_id),
        CONSTRAINT fk_enrollments_class FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE CASCADE,
        CONSTRAINT fk_enrollments_student FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS schedules (
        schedule_id INT AUTO_INCREMENT PRIMARY KEY,
        class_id INT NOT NULL,
        schedule_date VARCHAR(20) NOT NULL,
        start_time VARCHAR(10) NOT NULL,
        end_time VARCHAR(10) NOT NULL,
        room VARCHAR(50),
        schedule_type VARCHAR(20) NOT NULL DEFAULT 'regular',
        status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
        original_schedule_id INT,
        cancel_reason TEXT,
        created_at VARCHAR(30) NOT NULL,
        updated_at VARCHAR(30) NOT NULL,
        CONSTRAINT fk_schedules_class FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE CASCADE,
        CONSTRAINT fk_schedules_original FOREIGN KEY (original_schedule_id) REFERENCES schedules(schedule_id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

# Schema SQLite tương thích cho môi trường demo / kiểm thử độc lập
SCHEMA_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department_id INTEGER REFERENCES departments(department_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lecturers (
    lecturer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department_id INTEGER REFERENCES departments(department_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_name TEXT NOT NULL UNIQUE,
    department_id INTEGER REFERENCES departments(department_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classes (
    class_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL UNIQUE,
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    lecturer_id INTEGER REFERENCES lecturers(lecturer_id),
    semester TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(class_id),
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    created_at TEXT NOT NULL,
    UNIQUE (class_id, student_id)
);
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(class_id),
    schedule_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    room TEXT,
    schedule_type TEXT NOT NULL DEFAULT 'regular',
    status TEXT NOT NULL DEFAULT 'scheduled',
    original_schedule_id INTEGER REFERENCES schedules(schedule_id),
    cancel_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_db_type():
    """Xác định loại cơ sở dữ liệu: 'mysql' hoặc 'sqlite'."""
    if has_app_context():
        if current_app.config.get("DATABASE_TYPE"):
            return current_app.config["DATABASE_TYPE"].lower()
        if current_app.config.get("DB_TYPE"):
            return current_app.config["DB_TYPE"].lower()
        if current_app.config.get("MYSQL_HOST") or current_app.config.get("MYSQL_DB"):
            return "mysql"
        if current_app.config.get("database_path"):
            return "sqlite"
    if os.environ.get("DATABASE_TYPE"):
        return os.environ["DATABASE_TYPE"].lower()
    if os.environ.get("DB_TYPE"):
        return os.environ["DB_TYPE"].lower()
    if os.environ.get("MYSQL_HOST") or os.environ.get("MYSQL_DB"):
        return "mysql"
    return "mysql" if pymysql is not None else "sqlite"


def get_connection_db_type(connection):
    """Xác định loại database từ đối tượng connection."""
    if pymysql and isinstance(connection, pymysql.connections.Connection):
        return "mysql"
    return "sqlite"


def get_db_connection():
    """Lấy kết nối cơ sở dữ liệu MySQL (theo thống nhất nhóm) hoặc SQLite dự phòng."""
    db_type = get_db_type()
    if db_type == "mysql" and pymysql is not None:
        try:
            cfg = current_app.config if has_app_context() else {}
            host = cfg.get("MYSQL_HOST", os.environ.get("MYSQL_HOST", "localhost"))
            user = cfg.get("MYSQL_USER", os.environ.get("MYSQL_USER", "root"))
            password = cfg.get("MYSQL_PASSWORD", os.environ.get("MYSQL_PASSWORD", ""))
            db = cfg.get("MYSQL_DB", os.environ.get("MYSQL_DB", "student_attendance"))
            port = int(cfg.get("MYSQL_PORT", os.environ.get("MYSQL_PORT", 3306)))
            charset = cfg.get("MYSQL_CHARSET", os.environ.get("MYSQL_CHARSET", "utf8mb4"))

            connection = pymysql.connect(
                host=host,
                user=user,
                password=password,
                database=db,
                port=port,
                charset=charset,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
            )
            return connection
        except Exception:
            # Fallback sang SQLite khi chưa bật MySQL server
            return get_sqlite_connection()

    return get_sqlite_connection()


def get_sqlite_connection():
    """Kết nối SQLite dự phòng cho demo / offline testing."""
    if has_app_context() and current_app.config.get("SQLITE_DB_PATH"):
        database_path = current_app.config["SQLITE_DB_PATH"]
    elif has_app_context() and current_app.config.get("database_path"):
        database_path = current_app.config["database_path"]
    else:
        database_path = os.environ.get("SQLITE_DB_PATH", os.environ.get("attendance_database_path", "demo.db"))
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def adapt_sql(sql, db_type):
    """Chuyển đổi placeholder '?' sang '%s' nếu đang dùng MySQL."""
    if db_type == "mysql":
        return sql.replace("?", "%s")
    return sql


def init_academic_tables():
    """Khởi tạo bảng cơ sở dữ liệu (tương thích MySQL và SQLite)."""
    connection = get_db_connection()
    db_type = get_connection_db_type(connection)
    try:
        if db_type == "mysql":
            with connection.cursor() as cursor:
                for statement in SCHEMA_SQL_MYSQL:
                    cleaned_stmt = statement.strip()
                    if cleaned_stmt:
                        cursor.execute(cleaned_stmt)
            connection.commit()
        else:
            connection.executescript(SCHEMA_SQL_SQLITE)
            connection.commit()
    finally:
        connection.close()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_one(sql, params=()):
    """Truy vấn 1 bản ghi; trả về dictionary hoặc None."""
    connection = get_db_connection()
    db_type = get_connection_db_type(connection)
    try:
        adapted_sql = adapt_sql(sql, db_type)
        if db_type == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(adapted_sql, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        else:
            row = connection.execute(adapted_sql, params).fetchone()
            return dict(row) if row else None
    finally:
        connection.close()


def fetch_all(sql, params=()):
    """Truy vấn danh sách bản ghi; trả về list of dicts."""
    connection = get_db_connection()
    db_type = get_connection_db_type(connection)
    try:
        adapted_sql = adapt_sql(sql, db_type)
        if db_type == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(adapted_sql, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        else:
            rows = connection.execute(adapted_sql, params).fetchall()
            return [dict(row) for row in rows]
    finally:
        connection.close()


def run_write(sql, params=()):
    """Chạy lệnh ghi (INSERT/UPDATE/DELETE); trả về lastrowid. Đổi lỗi sang academic_error."""
    connection = get_db_connection()
    db_type = get_connection_db_type(connection)
    try:
        adapted_sql = adapt_sql(sql, db_type)
        if db_type == "mysql":
            with connection.cursor() as cursor:
                cursor.execute(adapted_sql, params)
                connection.commit()
                return cursor.lastrowid
        else:
            cursor = connection.execute(adapted_sql, params)
            connection.commit()
            return cursor.lastrowid
    except Exception as error:
        try:
            connection.rollback()
        except Exception:
            pass
        raise academic_error(explain_integrity_error(str(error))) from error
    finally:
        connection.close()


def explain_integrity_error(message):
    upper_msg = message.upper()
    if "UNIQUE" in upper_msg or "1062" in upper_msg or "DUPLICATE ENTRY" in upper_msg:
        return "Dữ liệu bị trùng với bản ghi đã có (tên, email hoặc tài khoản đã tồn tại)."
    if "FOREIGN KEY" in upper_msg or "1452" in upper_msg or "1217" in upper_msg or "1451" in upper_msg:
        return "Dữ liệu liên kết không tồn tại hoặc đang được sử dụng ở bảng khác."
    return "Dữ liệu không hợp lệ hoặc vi phạm ràng buộc cơ sở dữ liệu."


def clean_data(data, allowed_fields):
    """Chỉ giữ các key cho phép; cắt khoảng trắng; chuỗi rỗng thành None."""
    cleaned = {}
    for field_name in allowed_fields:
        if field_name in (data or {}):
            value = data[field_name]
            if isinstance(value, str):
                value = value.strip()
            cleaned[field_name] = value if value != "" else None
    return cleaned


def check_required(data, required_fields, labels=None):
    labels = labels or {}
    missing = [labels.get(name, name) for name in required_fields if data.get(name) is None]
    if missing:
        raise academic_error("Thiếu dữ liệu bắt buộc: " + ", ".join(missing) + ".")


def check_email(email):
    if email is not None and not EMAIL_PATTERN.match(email):
        raise academic_error("Email không hợp lệ.")


def to_int_or_none(data, field_names):
    for field_name in field_names:
        value = data.get(field_name)
        if value is None:
            continue
        try:
            data[field_name] = int(value)
        except (TypeError, ValueError):
            raise academic_error("Giá trị của " + field_name + " phải là số nguyên.")


def insert_record(table, data, allowed_fields, required_fields, labels=None, has_updated_at=True):
    data = clean_data(data, allowed_fields)
    check_required(data, required_fields, labels)
    data["created_at"] = now_text()
    if has_updated_at:
        data["updated_at"] = data["created_at"]
    column_names = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    return run_write(
        "INSERT INTO " + table + " (" + column_names + ") VALUES (" + placeholders + ")",
        tuple(data.values()),
    )


def update_record(table, key_column, key_value, data, allowed_fields, required_fields=(), labels=None):
    data = clean_data(data, allowed_fields)
    for field_name in required_fields:
        if field_name in data and data[field_name] is None:
            raise academic_error("Thiếu dữ liệu bắt buộc: " + (labels or {}).get(field_name, field_name) + ".")
    if not data:
        raise academic_error("Không có dữ liệu để cập nhật.")
    data["updated_at"] = now_text()
    assignments = ", ".join(name + " = ?" for name in data)
    run_write(
        "UPDATE " + table + " SET " + assignments + " WHERE " + key_column + " = ?",
        tuple(data.values()) + (key_value,),
    )


# ---------- Khoa/phòng ban ----------
DEPARTMENT_FIELDS = ["department_name"]


def get_department_by_id(department_id):
    return fetch_one("SELECT * FROM departments WHERE department_id = ?", (department_id,))


def get_department_list():
    return fetch_all("SELECT * FROM departments ORDER BY department_name")


def create_department(department_data):
    department_id = insert_record(
        "departments", department_data, DEPARTMENT_FIELDS, ["department_name"],
        {"department_name": "tên khoa/phòng ban"},
    )
    return get_department_by_id(department_id)


def update_department(department_id, department_data):
    if get_department_by_id(department_id) is None:
        raise academic_error("Không tìm thấy khoa/phòng ban.")
    update_record("departments", "department_id", department_id, department_data,
                  DEPARTMENT_FIELDS, ["department_name"], {"department_name": "tên khoa/phòng ban"})
    return get_department_by_id(department_id)


def delete_department(department_id):
    """Xóa khoa/phòng ban (kiểm tra an toàn dữ liệu liên kết)."""
    if get_department_by_id(department_id) is None:
        raise academic_error("Không tìm thấy khoa/phòng ban.")
    if fetch_one("SELECT 1 FROM students WHERE department_id = ?", (department_id,)):
        raise academic_error("Không thể xóa: Khoa/phòng ban đang có sinh viên trực thuộc.")
    if fetch_one("SELECT 1 FROM lecturers WHERE department_id = ?", (department_id,)):
        raise academic_error("Không thể xóa: Khoa/phòng ban đang có giảng viên trực thuộc.")
    if fetch_one("SELECT 1 FROM courses WHERE department_id = ?", (department_id,)):
        raise academic_error("Không thể xóa: Khoa/phòng ban đang có môn học trực thuộc.")
    run_write("DELETE FROM departments WHERE department_id = ?", (department_id,))
    return True


# ---------- Môn học ----------
COURSE_FIELDS = ["course_name", "department_id"]
COURSE_SELECT = """
    SELECT courses.*, departments.department_name
    FROM courses LEFT JOIN departments ON departments.department_id = courses.department_id
"""


def get_course_by_id(course_id):
    return fetch_one(COURSE_SELECT + " WHERE courses.course_id = ?", (course_id,))


def get_course_list(filters=None):
    filters = filters or {}
    sql, params = COURSE_SELECT + " WHERE 1 = 1", []
    if filters.get("department_id"):
        sql += " AND courses.department_id = ?"
        params.append(filters["department_id"])
    return fetch_all(sql + " ORDER BY courses.course_name", tuple(params))


def create_course(course_data):
    course_data = clean_data(course_data, COURSE_FIELDS)
    to_int_or_none(course_data, ["department_id"])
    course_id = insert_record("courses", course_data, COURSE_FIELDS, ["course_name"],
                              {"course_name": "tên môn học"})
    return get_course_by_id(course_id)


def update_course(course_id, course_data):
    if get_course_by_id(course_id) is None:
        raise academic_error("Không tìm thấy môn học.")
    course_data = clean_data(course_data, COURSE_FIELDS)
    to_int_or_none(course_data, ["department_id"])
    update_record("courses", "course_id", course_id, course_data, COURSE_FIELDS,
                  ["course_name"], {"course_name": "tên môn học"})
    return get_course_by_id(course_id)


def delete_course(course_id):
    """Xóa môn học (kiểm tra an toàn lớp học phần liên kết)."""
    if get_course_by_id(course_id) is None:
        raise academic_error("Không tìm thấy môn học.")
    if fetch_one("SELECT 1 FROM classes WHERE course_id = ?", (course_id,)):
        raise academic_error("Không thể xóa: Môn học đang có lớp học phần trực thuộc.")
    run_write("DELETE FROM courses WHERE course_id = ?", (course_id,))
    return True


# ---------- Lớp học phần ----------
CLASS_FIELDS = ["class_name", "course_id", "lecturer_id", "semester"]
CLASS_LABELS = {"class_name": "tên lớp học phần", "course_id": "môn học"}
CLASS_SELECT = """
    SELECT classes.*, courses.course_name, lecturers.full_name AS lecturer_name,
           (SELECT COUNT(*) FROM enrollments WHERE enrollments.class_id = classes.class_id) AS student_count
    FROM classes
    JOIN courses ON courses.course_id = classes.course_id
    LEFT JOIN lecturers ON lecturers.lecturer_id = classes.lecturer_id
"""


def get_class_by_id(class_id):
    return fetch_one(CLASS_SELECT + " WHERE classes.class_id = ?", (class_id,))


def get_class_list(filters=None):
    """filters: lecturer_id, course_id, semester (đều không bắt buộc)."""
    filters = filters or {}
    sql, params = CLASS_SELECT + " WHERE 1 = 1", []
    for field_name in ("lecturer_id", "course_id", "semester"):
        if filters.get(field_name):
            sql += " AND classes." + field_name + " = ?"
            params.append(filters[field_name])
    return fetch_all(sql + " ORDER BY classes.class_name", tuple(params))


def create_class(class_data):
    class_data = clean_data(class_data, CLASS_FIELDS)
    to_int_or_none(class_data, ["course_id", "lecturer_id"])
    class_id = insert_record("classes", class_data, CLASS_FIELDS, ["class_name", "course_id"], CLASS_LABELS)
    return get_class_by_id(class_id)


def update_class(class_id, class_data):
    if get_class_by_id(class_id) is None:
        raise academic_error("Không tìm thấy lớp học phần.")
    class_data = clean_data(class_data, CLASS_FIELDS)
    to_int_or_none(class_data, ["course_id", "lecturer_id"])
    update_record("classes", "class_id", class_id, class_data, CLASS_FIELDS,
                  ["class_name", "course_id"], CLASS_LABELS)
    return get_class_by_id(class_id)


def delete_class(class_id):
    """Xóa lớp học phần (kiểm tra sinh viên đăng ký và lịch học)."""
    if get_class_by_id(class_id) is None:
        raise academic_error("Không tìm thấy lớp học phần.")
    if fetch_one("SELECT 1 FROM enrollments WHERE class_id = ?", (class_id,)):
        raise academic_error("Không thể xóa: Lớp học phần đang có sinh viên đăng ký.")
    if fetch_one("SELECT 1 FROM schedules WHERE class_id = ?", (class_id,)):
        raise academic_error("Không thể xóa: Lớp học phần đã có lịch học.")
    run_write("DELETE FROM classes WHERE class_id = ?", (class_id,))
    return True


# ---------- Đăng ký học ----------
def get_enrollment_list(class_id):
    """Danh sách sinh viên đăng ký lớp; list rỗng nếu chưa có ai."""
    return fetch_all(
        """
        SELECT students.student_id, students.user_id, students.full_name, students.email,
               enrollments.enrollment_id
        FROM enrollments JOIN students ON students.student_id = enrollments.student_id
        WHERE enrollments.class_id = ?
        ORDER BY students.full_name
        """,
        (class_id,),
    )


def add_student_to_class(class_id, student_id):
    if get_class_by_id(class_id) is None:
        raise academic_error("Không tìm thấy lớp học phần.")
    if fetch_one("SELECT 1 FROM students WHERE student_id = ?", (student_id,)) is None:
        raise academic_error("Không tìm thấy sinh viên.")
    if fetch_one("SELECT 1 FROM enrollments WHERE class_id = ? AND student_id = ?", (class_id, student_id)):
        raise academic_error("Sinh viên đã có trong lớp học phần này.")
    run_write("INSERT INTO enrollments (class_id, student_id, created_at) VALUES (?, ?, ?)",
              (class_id, student_id, now_text()))
    return True


def remove_student_from_class(class_id, student_id):
    if fetch_one("SELECT 1 FROM enrollments WHERE class_id = ? AND student_id = ?", (class_id, student_id)) is None:
        raise academic_error("Sinh viên không có trong lớp học phần này.")
    run_write("DELETE FROM enrollments WHERE class_id = ? AND student_id = ?", (class_id, student_id))
    return True
