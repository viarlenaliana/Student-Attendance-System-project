"""Quản lý thông tin giảng viên (Admin)."""
from app.models.academic import (
    academic_error, check_email, check_required, clean_data, fetch_all, fetch_one,
    insert_record, to_int_or_none, update_record,
)

LECTURER_FIELDS = ["user_id", "full_name", "email", "department_id"]
LECTURER_LABELS = {"full_name": "họ tên", "email": "email"}
LECTURER_SELECT = """
    SELECT lecturers.*, departments.department_name
    FROM lecturers LEFT JOIN departments ON departments.department_id = lecturers.department_id
"""


def get_lecturer_by_id(lecturer_id):
    return fetch_one(LECTURER_SELECT + " WHERE lecturers.lecturer_id = ?", (lecturer_id,))


def get_lecturer_list(filters=None):
    """filters: department_id, keyword (tìm theo họ tên/email)."""
    filters = filters or {}
    sql, params = LECTURER_SELECT + " WHERE 1 = 1", []
    if filters.get("department_id"):
        sql += " AND lecturers.department_id = ?"
        params.append(filters["department_id"])
    if filters.get("keyword"):
        sql += " AND (lecturers.full_name LIKE ? OR lecturers.email LIKE ?)"
        params += ["%" + filters["keyword"] + "%"] * 2
    return fetch_all(sql + " ORDER BY lecturers.full_name", tuple(params))


def create_lecturer(lecturer_data):
    lecturer_data = clean_data(lecturer_data, LECTURER_FIELDS)
    check_required(lecturer_data, ["full_name", "email"], LECTURER_LABELS)
    check_email(lecturer_data["email"])
    to_int_or_none(lecturer_data, ["user_id", "department_id"])
    lecturer_id = insert_record("lecturers", lecturer_data, LECTURER_FIELDS,
                               ["full_name", "email"], LECTURER_LABELS)
    return get_lecturer_by_id(lecturer_id)


def update_lecturer(lecturer_id, lecturer_data):
    if get_lecturer_by_id(lecturer_id) is None:
        raise academic_error("Không tìm thấy giảng viên.")
    lecturer_data = clean_data(lecturer_data, LECTURER_FIELDS)
    check_email(lecturer_data.get("email"))
    to_int_or_none(lecturer_data, ["user_id", "department_id"])
    update_record("lecturers", "lecturer_id", lecturer_id, lecturer_data, LECTURER_FIELDS,
                  ["full_name", "email"], LECTURER_LABELS)
    return get_lecturer_by_id(lecturer_id)
