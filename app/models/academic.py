"""Dữ liệu học tập: khoa/phòng ban, môn học, lớp học phần, đăng ký học.

Quản lý kết nối cơ sở dữ liệu và schema dùng chung cho student, lecturer, schedule.
"""
import os
import re
import sqlite3
from datetime import datetime

from flask import current_app, has_app_context


class academic_error(Exception):
    """Lỗi dữ liệu/nghiệp vụ; message hiển thị được cho người dùng."""


SCHEMA_SQL = """
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


def get_db_connection():
    if has_app_context() and current_app.config.get("database_path"):
        database_path = current_app.config["database_path"]
    else:
        database_path = os.environ.get("attendance_database_path", "attendance.db")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_academic_tables():
    connection = get_db_connection()
    try:
        connection.executescript(SCHEMA_SQL)
        connection.commit()
    finally:
        connection.close()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_one(sql, params=()):
    connection = get_db_connection()
    try:
        row = connection.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def fetch_all(sql, params=()):
    connection = get_db_connection()
    try:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]
    finally:
        connection.close()


def run_write(sql, params=()):
    """Chạy một lệnh ghi; trả về lastrowid. Đổi lỗi database thành academic_error."""
    connection = get_db_connection()
    try:
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise academic_error(explain_integrity_error(str(error))) from error
    finally:
        connection.close()


def explain_integrity_error(message):
    if "UNIQUE" in message:
        return "Dữ liệu bị trùng với bản ghi đã có (tên, email hoặc tài khoản đã tồn tại)."
    if "FOREIGN KEY" in message:
        return "Dữ liệu liên kết không tồn tại hoặc đang được sử dụng."
    return "Dữ liệu không hợp lệ."


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
