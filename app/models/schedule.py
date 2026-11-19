"""Quản lý lịch học, lịch học bù, hủy lịch.

schedule_type: 'regular' | 'makeup'; status: 'scheduled' | 'cancelled'.
Lịch đã hủy không bị xóa khỏi cơ sở dữ liệu, chỉ chuyển status = 'cancelled'.
"""
from datetime import datetime

from app.models.academic import (
    academic_error, check_required, clean_data, fetch_all, fetch_one, get_class_by_id,
    insert_record, now_text, run_write, to_int_or_none, update_record,
)

SCHEDULE_FIELDS = ["class_id", "schedule_date", "start_time", "end_time", "room"]
SCHEDULE_LABELS = {
    "class_id": "lớp học phần", "schedule_date": "ngày học",
    "start_time": "giờ bắt đầu", "end_time": "giờ kết thúc",
}
SCHEDULE_SELECT = """
    SELECT schedules.*, classes.class_name, classes.lecturer_id, courses.course_name
    FROM schedules
    JOIN classes ON classes.class_id = schedules.class_id
    JOIN courses ON courses.course_id = classes.course_id
"""


def check_schedule_time(schedule_data):
    try:
        if schedule_data.get("schedule_date"):
            datetime.strptime(schedule_data["schedule_date"], "%Y-%m-%d")
        start = datetime.strptime(schedule_data["start_time"], "%H:%M") if schedule_data.get("start_time") else None
        end = datetime.strptime(schedule_data["end_time"], "%H:%M") if schedule_data.get("end_time") else None
    except ValueError:
        raise academic_error("Ngày phải có dạng YYYY-MM-DD và giờ phải có dạng HH:MM.")
    if start and end and start >= end:
        raise academic_error("Giờ kết thúc phải sau giờ bắt đầu.")


def get_schedule_by_id(schedule_id):
    return fetch_one(SCHEDULE_SELECT + " WHERE schedules.schedule_id = ?", (schedule_id,))


def get_schedule_list(filters=None):
    """filters: class_id, lecturer_id, student_id, status, date_from, date_to.

    Mặc định trả cả lịch đã hủy (status = 'cancelled'); truyền status để lọc.
    """
    filters = filters or {}
    sql, params = SCHEDULE_SELECT + " WHERE 1 = 1", []
    if filters.get("class_id"):
        sql += " AND schedules.class_id = ?"
        params.append(filters["class_id"])
    if filters.get("lecturer_id"):
        sql += " AND classes.lecturer_id = ?"
        params.append(filters["lecturer_id"])
    if filters.get("student_id"):
        sql += " AND schedules.class_id IN (SELECT class_id FROM enrollments WHERE student_id = ?)"
        params.append(filters["student_id"])
    if filters.get("status"):
        sql += " AND schedules.status = ?"
        params.append(filters["status"])
    if filters.get("date_from"):
        sql += " AND schedules.schedule_date >= ?"
        params.append(filters["date_from"])
    if filters.get("date_to"):
        sql += " AND schedules.schedule_date <= ?"
        params.append(filters["date_to"])
    return fetch_all(sql + " ORDER BY schedules.schedule_date, schedules.start_time", tuple(params))


def create_schedule_record(schedule_data, schedule_type, original_schedule_id=None):
    schedule_data = clean_data(schedule_data, SCHEDULE_FIELDS)
    check_required(schedule_data, ["class_id", "schedule_date", "start_time", "end_time"], SCHEDULE_LABELS)
    to_int_or_none(schedule_data, ["class_id"])
    check_schedule_time(schedule_data)
    if get_class_by_id(schedule_data["class_id"]) is None:
        raise academic_error("Không tìm thấy lớp học phần.")
    fields = list(SCHEDULE_FIELDS)
    schedule_data["schedule_type"] = schedule_type
    fields.append("schedule_type")
    if original_schedule_id is not None:
        schedule_data["original_schedule_id"] = original_schedule_id
        fields.append("original_schedule_id")
    schedule_id = insert_record("schedules", schedule_data, fields,
                                ["class_id", "schedule_date", "start_time", "end_time"], SCHEDULE_LABELS)
    return get_schedule_by_id(schedule_id)


def create_schedule(schedule_data):
    return create_schedule_record(schedule_data, "regular")


def create_makeup_schedule(schedule_data):
    """Lịch học bù. schedule_data có thể kèm original_schedule_id (lịch được học bù)."""
    original_schedule_id = (schedule_data or {}).get("original_schedule_id")
    if original_schedule_id not in (None, ""):
        try:
            original_schedule_id = int(original_schedule_id)
        except (TypeError, ValueError):
            raise academic_error("Mã lịch gốc không hợp lệ.")
        if get_schedule_by_id(original_schedule_id) is None:
            raise academic_error("Không tìm thấy lịch gốc.")
    else:
        original_schedule_id = None
    return create_schedule_record(schedule_data, "makeup", original_schedule_id)


def update_schedule(schedule_id, schedule_data):
    current = get_schedule_by_id(schedule_id)
    if current is None:
        raise academic_error("Không tìm thấy lịch học.")
    if current["status"] == "cancelled":
        raise academic_error("Lịch đã hủy không thể cập nhật.")
    schedule_data = clean_data(schedule_data, SCHEDULE_FIELDS)
    to_int_or_none(schedule_data, ["class_id"])
    merged = {**current, **schedule_data}
    check_schedule_time(merged)
    if "class_id" in schedule_data and get_class_by_id(schedule_data["class_id"]) is None:
        raise academic_error("Không tìm thấy lớp học phần.")
    update_record("schedules", "schedule_id", schedule_id, schedule_data, SCHEDULE_FIELDS,
                  ["class_id", "schedule_date", "start_time", "end_time"], SCHEDULE_LABELS)
    return get_schedule_by_id(schedule_id)


def cancel_schedule(schedule_id, reason=None):
    current = get_schedule_by_id(schedule_id)
    if current is None:
        raise academic_error("Không tìm thấy lịch học.")
    if current["status"] == "cancelled":
        raise academic_error("Lịch này đã được hủy trước đó.")
    run_write(
        "UPDATE schedules SET status = 'cancelled', cancel_reason = ?, updated_at = ? WHERE schedule_id = ?",
        ((reason or "").strip() or None, now_text(), schedule_id),
    )
    return get_schedule_by_id(schedule_id)
