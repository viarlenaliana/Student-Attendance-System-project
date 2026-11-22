"""Controller xem và cập nhật trạng thái thông báo trong ứng dụng."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from app.models.notification import (
    NOTIFICATION_TYPE_LABELS,
    get_notification_by_id,
    get_unread_notification_count,
    get_user_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
    notification_error,
)
from app.models.user import get_current_user
from app.routes.auth import login_required

notification_bp = Blueprint("notification", __name__, url_prefix="/notifications")


@notification_bp.route("/")
@notification_bp.route("")
@login_required
def notification_list_page():
    user = get_current_user()
    selected_type = request.args.get("notification_type", "").strip()
    unread_only = request.args.get("unread_only", "").strip() in ("1", "true")
    notifications = get_user_notifications(
        user["user_id"],
        unread_only=unread_only,
        notification_type=selected_type or None,
    )
    unread_count = get_unread_notification_count(user["user_id"])
    return render_template(
        "notifications/index.html",
        notifications=notifications,
        unread_count=unread_count,
        selected_type=selected_type,
        unread_only=unread_only,
        type_labels=NOTIFICATION_TYPE_LABELS,
    )


@notification_bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read_action(notification_id):
    user = get_current_user()
    notification = get_notification_by_id(notification_id)
    if notification is None:
        abort(404)
    if int(notification["user_id"]) != int(user["user_id"]):
        abort(403)

    try:
        mark_notification_as_read(notification_id, user["user_id"])
    except notification_error as error:
        flash(str(error), "danger")
    else:
        flash("Đã đánh dấu thông báo là đã đọc.", "success")
    return redirect(url_for("notification.notification_list_page"))


@notification_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read_action():
    user = get_current_user()
    mark_all_notifications_as_read(user["user_id"])
    flash("Đã đánh dấu tất cả thông báo là đã đọc.", "success")
    return redirect(url_for("notification.notification_list_page"))


@notification_bp.route("/unread-count")
@login_required
def unread_count_api():
    user = get_current_user()
    return jsonify({"unread_count": get_unread_notification_count(user["user_id"])})
