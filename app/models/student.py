"""Quản lý thông tin sinh viên (Admin)."""
from app.models.academic import (
    academic_error, check_email, check_required, clean_data, fetch_all, fetch_one,
    insert_record, to_int_or_none, update_record,
)

STUDENT_FIELDS = ["user_id", "full_name", "email", "department_id"]
STUDENT_LABELS = {"full_name": "họ tên", "email": "email"}
STUDENT_SELECT = """
    SELECT students.*, departments.department_name
    FROM students LEFT JOIN departments ON departments.department_id = students.department_id
"""


def get_student_by_id(student_id):
    return fetch_one(STUDENT_SELECT + " WHERE students.student_id = ?", (student_id,))


def get_student_list(filters=None):
    """filters: department_id, keyword (tìm theo họ tên/email)."""
    filters = filters or {}
    sql, params = STUDENT_SELECT + " WHERE 1 = 1", []
    if filters.get("department_id"):
        sql += " AND students.department_id = ?"
        params.append(filters["department_id"])
    if filters.get("keyword"):
        sql += " AND (students.full_name LIKE ? OR students.email LIKE ?)"
        params += ["%" + filters["keyword"] + "%"] * 2
    return fetch_all(sql + " ORDER BY students.full_name", tuple(params))


def create_student(student_data):
    student_data = clean_data(student_data, STUDENT_FIELDS)
    check_required(student_data, ["full_name", "email"], STUDENT_LABELS)
    check_email(student_data["email"])
    to_int_or_none(student_data, ["user_id", "department_id"])
    student_id = insert_record("students", student_data, STUDENT_FIELDS,
                               ["full_name", "email"], STUDENT_LABELS)
    return get_student_by_id(student_id)


def update_student(student_id, student_data):
    if get_student_by_id(student_id) is None:
        raise academic_error("Không tìm thấy sinh viên.")
    student_data = clean_data(student_data, STUDENT_FIELDS)
    check_email(student_data.get("email"))
    to_int_or_none(student_data, ["user_id", "department_id"])
    update_record("students", "student_id", student_id, student_data, STUDENT_FIELDS,
                  ["full_name", "email"], STUDENT_LABELS)
    return get_student_by_id(student_id)
