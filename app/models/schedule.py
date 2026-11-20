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


def check_schedule_conflict(schedule_data, exclude_schedule_id=None):
    """Kiểm tra xung đột lịch học: trùng phòng, trùng lớp, hoặc trùng giảng viên.

    Điều kiện xung đột thời gian trong cùng một ngày:
    start_time < other.end_time AND end_time > other.start_time
    Chỉ xét các lịch đang hoạt động (status != 'cancelled').
    """
    class_id = schedule_data.get("class_id")
    schedule_date = schedule_data.get("schedule_date")
    start_time = schedule_data.get("start_time")
    end_time = schedule_data.get("end_time")
    room = (schedule_data.get("room") or "").strip()

    if not (class_id and schedule_date and start_time and end_time):
        return

    class_info = get_class_by_id(class_id)
    lecturer_id = class_info.get("lecturer_id") if class_info else None

    # Lấy tất cả lịch cùng ngày đang hoạt động (trừ chính nó nếu đang cập nhật)
    sql = """
        SELECT schedules.*, classes.class_name, classes.lecturer_id
        FROM schedules
        JOIN classes ON classes.class_id = schedules.class_id
        WHERE schedules.schedule_date = ?
          AND schedules.status != 'cancelled'
          AND schedules.start_time < ?
          AND schedules.end_time > ?
    """
    params = [schedule_date, end_time, start_time]
    if exclude_schedule_id:
        sql += " AND schedules.schedule_id != ?"
        params.append(exclude_schedule_id)

    conflicts = fetch_all(sql, tuple(params))
    for c in conflicts:
        if c["class_id"] == class_id:
            raise academic_error(
                f"Xung đột lịch: Lớp '{c['class_name']}' đã có lịch học vào khung giờ {c['start_time']}-{c['end_time']} ngày {schedule_date}."
            )
        if room and c.get("room") and c["room"].strip().lower() == room.lower():
            raise academic_error(
                f"Xung đột phòng học: Phòng '{room}' đã được sử dụng bởi lớp '{c['class_name']}' vào khung giờ {c['start_time']}-{c['end_time']} ngày {schedule_date}."
            )
        if lecturer_id and c.get("lecturer_id") == lecturer_id:
            raise academic_error(
                f"Xung đột giảng viên: Giảng viên phụ trách đã có lịch dạy lớp '{c['class_name']}' vào khung giờ {c['start_time']}-{c['end_time']} ngày {schedule_date}."
            )


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

    # Kiểm tra xung đột lịch học
    check_schedule_conflict(schedule_data)

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
    """Tạo lịch học bù.

    Ràng buộc nghiệp vụ:
    - Bắt buộc phải có mã lịch gốc (original_schedule_id)
    - Lịch gốc phải tồn tại trong hệ thống
    - Lịch gốc không được ở trạng thái 'cancelled'
    - Lịch bù phải thuộc cùng lớp học phần với lịch gốc
    """
    original_id_raw = (schedule_data or {}).get("original_schedule_id")
    if original_id_raw in (None, ""):
        raise academic_error("Bắt buộc phải chọn lịch gốc để tạo lịch học bù.")

    try:
        original_schedule_id = int(original_id_raw)
    except (TypeError, ValueError):
        raise academic_error("Mã lịch gốc không hợp lệ.")

    original_schedule = get_schedule_by_id(original_schedule_id)
    if original_schedule is None:
        raise academic_error("Không tìm thấy lịch gốc.")

    if original_schedule.get("status") == "cancelled":
        raise academic_error("Không thể tạo lịch học bù cho lịch đã bị hủy.")

    class_id = schedule_data.get("class_id")
    if class_id is not None:
        try:
            class_id = int(class_id)
        except (TypeError, ValueError):
            pass
    if class_id and class_id != original_schedule["class_id"]:
        raise academic_error("Lịch học bù phải thuộc cùng lớp học phần với lịch gốc.")

    # Đảm bảo class_id trùng với lịch gốc
    schedule_data["class_id"] = original_schedule["class_id"]

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

    # Kiểm tra xung đột lịch học khi cập nhật (loại trừ chính bản ghi này)
    check_schedule_conflict(merged, exclude_schedule_id=schedule_id)

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
