"""Controller xem nhật ký hoạt động (chỉ Admin được xem; cấm mọi hành vi sửa/xóa log)."""
from flask import Blueprint, abort, render_template, request

from app.models.activity_log import (
    get_activity_logs,
    get_distinct_log_actions,
    get_distinct_log_object_types,
)
from app.routes.auth import login_required, role_required

activity_log_bp = Blueprint("activity_log", __name__, url_prefix="/admin/activity-logs")


@activity_log_bp.route("/")
@activity_log_bp.route("")
@role_required("admin")
def activity_log_list_page():
    filters = {
        "username": request.args.get("username", "").strip(),
        "action": request.args.get("action", "").strip(),
        "object_type": request.args.get("object_type", "").strip(),
        "result": request.args.get("result", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }
    logs = get_activity_logs(filters)
    return render_template(
        "admin/activity_logs.html",
        logs=logs,
        filters=filters,
        available_actions=get_distinct_log_actions(),
        available_object_types=get_distinct_log_object_types(),
    )


@activity_log_bp.route("/<int:log_id>/edit", methods=["GET", "POST", "PUT", "PATCH"])
@activity_log_bp.route("/<int:log_id>/delete", methods=["GET", "POST", "DELETE"])
@login_required
def forbid_log_modification(log_id):
    """Chặn tuyệt đối mọi yêu cầu chỉnh sửa hoặc xóa nhật ký hoạt động."""
    abort(403)
