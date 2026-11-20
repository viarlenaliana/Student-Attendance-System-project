"""admin: lịch học, lịch học bù, hủy lịch."""
import logging
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models.academic import academic_error, get_class_list, get_enrollment_list, get_class_by_id
from app.models.schedule import (
    cancel_schedule, create_makeup_schedule, create_schedule, get_schedule_list, update_schedule,
)
from app.models.student import get_student_by_id
from app.routes.academic import admin_required

# Tích hợp an toàn với các module của thành viên khác trong nhóm
try:
    from app.models.activity_log import create_activity_log
except ImportError:
    def create_activity_log(*args, **kwargs):
        pass

try:
    from app.models.notification import create_notification
except ImportError:
    def create_notification(*args, **kwargs):
        pass

try:
    from app.models.user import get_current_user
except ImportError:
    def get_current_user():
        return {"user_id": 1, "role": "admin"}

logger = logging.getLogger(__name__)

schedule_bp = Blueprint("schedule", __name__, url_prefix="/admin/schedules")


def notify_schedule_event(schedule_record, title, message):
    """Gửi thông báo lịch học cho giảng viên phụ trách và sinh viên trong lớp.
    
    Xử lý lỗi gửi thông báo để lỗi của một người nhận không làm gián đoạn
    những người nhận còn lại.
    """
    receiver_ids = []
    class_record = get_class_by_id(schedule_record["class_id"])
    if class_record and class_record.get("lecturer_id"):
        from app.models.lecturer import get_lecturer_by_id
        lecturer = get_lecturer_by_id(class_record["lecturer_id"])
        if lecturer and lecturer.get("user_id"):
            receiver_ids.append(lecturer["user_id"])
    for enrollment in get_enrollment_list(schedule_record["class_id"]):
        student = get_student_by_id(enrollment["student_id"])
        if student and student.get("user_id"):
            receiver_ids.append(student["user_id"])

    failed_receivers = []
    for receiver_id in receiver_ids:
        try:
            create_notification(receiver_id, title, message, "schedule")
        except Exception as err:
            logger.warning(f"Không thể gửi thông báo cho user {receiver_id}: {err}")
            failed_receivers.append(receiver_id)

    if failed_receivers:
        logger.info(f"Đã gửi thông báo với {len(failed_receivers)}/{len(receiver_ids)} người nhận gặp lỗi.")


def describe_schedule(schedule_record):
    return "{} - {} {}-{}".format(
        schedule_record["class_name"], schedule_record["schedule_date"],
        schedule_record["start_time"], schedule_record["end_time"],
    )


def run_schedule_action(action_function, success_message, notice_title, log_action):
    user = get_current_user()
    try:
        schedule_record = action_function()
    except academic_error as error:
        flash(str(error), "danger")
        create_activity_log(user["user_id"], log_action, "schedule", None, "failed")
        return redirect(url_for("schedule.schedule_list_page"))
    flash(success_message, "success")
    create_activity_log(user["user_id"], log_action, "schedule", schedule_record["schedule_id"], "success")
    try:
        notify_schedule_event(schedule_record, notice_title, describe_schedule(schedule_record))
    except Exception:  # lịch đã lưu; lỗi gửi thông báo không được làm mất kết quả lưu
        flash("Lịch đã được lưu nhưng chưa gửi được thông báo.", "warning")
    return redirect(url_for("schedule.schedule_list_page"))


@schedule_bp.route("/")
@schedule_bp.route("")
@admin_required
def schedule_list_page():
    filters = {key: request.args.get(key) for key in ("class_id", "status", "date_from", "date_to")}
    class_options = [{"value": item["class_id"], "label": item["class_name"] + " (" + item["course_name"] + ")"}
                     for item in get_class_list()]
    return render_template(
        "admin/schedule/schedules.html", schedules=get_schedule_list(filters),
        class_options=class_options, filters=filters,
    )


@schedule_bp.route("/create", methods=["POST"])
@admin_required
def schedule_create_action():
    form_data = request.form.to_dict()
    return run_schedule_action(lambda: create_schedule(form_data), "Đã tạo lịch học.",
                               "Lịch học mới", "create_schedule")


@schedule_bp.route("/makeup/create", methods=["POST"])
@admin_required
def makeup_schedule_create_action():
    form_data = request.form.to_dict()
    return run_schedule_action(lambda: create_makeup_schedule(form_data), "Đã tạo lịch học bù.",
                               "Lịch học bù mới", "create_makeup_schedule")


@schedule_bp.route("/<int:schedule_id>/update", methods=["POST"])
@admin_required
def schedule_update_action(schedule_id):
    form_data = request.form.to_dict()
    return run_schedule_action(lambda: update_schedule(schedule_id, form_data), "Đã cập nhật lịch học.",
                               "Lịch học thay đổi", "update_schedule")


@schedule_bp.route("/<int:schedule_id>/cancel", methods=["POST"])
@admin_required
def schedule_cancel_action(schedule_id):
    reason = request.form.get("reason")
    return run_schedule_action(lambda: cancel_schedule(schedule_id, reason), "Đã hủy lịch học.",
                               "Lịch học bị hủy", "cancel_schedule")
