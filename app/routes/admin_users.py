"""Controller Admin quản lý tài khoản Student và Lecturer (tạo, cập nhật, khóa/mở khóa)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models.activity_log import create_activity_log
from app.models.user import (
    ADMIN_CREATABLE_ROLES,
    auth_error,
    create_user,
    get_current_user,
    get_user_by_id,
    get_user_list,
    set_user_status,
    update_user,
)
from app.routes.auth import role_required

admin_users_bp = Blueprint("admin_users", __name__, url_prefix="/admin/users")


@admin_users_bp.route("/")
@admin_users_bp.route("")
@role_required("admin")
def user_list_page():
    filters = {
        "role": request.args.get("role", "").strip(),
        "status": request.args.get("status", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
    }
    users = get_user_list(filters)
    return render_template(
        "admin/users.html",
        users=users,
        filters=filters,
        current_user=get_current_user(),
    )


@admin_users_bp.route("/create", methods=["POST"])
@role_required("admin")
def user_create_action():
    admin_user = get_current_user()
    user_data = {
        "username": request.form.get("username", ""),
        "full_name": request.form.get("full_name", ""),
        "email": request.form.get("email", ""),
        "role": request.form.get("role", ""),
        "password": request.form.get("password", ""),
        "must_change_password": True,
    }

    try:
        created_user = create_user(user_data, allowed_roles=ADMIN_CREATABLE_ROLES)
    except auth_error as error:
        create_activity_log(
            admin_user["user_id"],
            "create_user",
            "user",
            None,
            "failed",
            details=f"Tạo tài khoản thất bại ({user_data.get('username', '').strip() or 'N/A'})",
        )
        flash(str(error), "danger")
        return redirect(url_for("admin_users.user_list_page"))

    create_activity_log(
        admin_user["user_id"],
        "create_user",
        "user",
        created_user["user_id"],
        "success",
        details=f"Tạo tài khoản {created_user['username']} ({created_user['role']})",
    )
    flash(
        f"Đã tạo tài khoản '{created_user['username']}' ({created_user['role']}). "
        "Người dùng sẽ phải đổi mật khẩu khi đăng nhập lần đầu.",
        "success",
    )
    return redirect(url_for("admin_users.user_list_page"))


@admin_users_bp.route("/<int:user_id>/update", methods=["POST"])
@role_required("admin")
def user_update_action(user_id):
    admin_user = get_current_user()
    target_user = get_user_by_id(user_id)
    if target_user is None:
        create_activity_log(
            admin_user["user_id"],
            "update_user",
            "user",
            user_id,
            "failed",
            details="Không tìm thấy tài khoản",
        )
        flash("Không tìm thấy tài khoản cần cập nhật.", "danger")
        return redirect(url_for("admin_users.user_list_page"))

    if target_user["role"] == "admin":
        create_activity_log(
            admin_user["user_id"],
            "update_user",
            "user",
            user_id,
            "failed",
            details="Từ chối cập nhật tài khoản admin từ màn hình quản lý Student/Lecturer",
        )
        flash("Màn hình này chỉ quản lý cập nhật tài khoản Student và Lecturer.", "danger")
        return redirect(url_for("admin_users.user_list_page"))

    update_data = {
        "full_name": request.form.get("full_name"),
        "email": request.form.get("email"),
        "role": request.form.get("role"),
    }
    new_initial_password = request.form.get("password", "")
    if new_initial_password:
        update_data["password"] = new_initial_password

    try:
        updated_user = update_user(user_id, update_data, allowed_roles=ADMIN_CREATABLE_ROLES)
    except auth_error as error:
        create_activity_log(
            admin_user["user_id"],
            "update_user",
            "user",
            user_id,
            "failed",
            details="Cập nhật tài khoản thất bại",
        )
        flash(str(error), "danger")
        return redirect(url_for("admin_users.user_list_page"))

    create_activity_log(
        admin_user["user_id"],
        "update_user",
        "user",
        updated_user["user_id"],
        "success",
        details=f"Cập nhật tài khoản {updated_user['username']} ({updated_user['role']})",
    )
    flash(f"Đã cập nhật tài khoản '{updated_user['username']}'.", "success")
    return redirect(url_for("admin_users.user_list_page"))


@admin_users_bp.route("/<int:user_id>/status", methods=["POST"])
@role_required("admin")
def user_status_action(user_id):
    admin_user = get_current_user()
    target_user = get_user_by_id(user_id)
    if target_user is None:
        create_activity_log(
            admin_user["user_id"],
            "set_user_status",
            "user",
            user_id,
            "failed",
            details="Không tìm thấy tài khoản",
        )
        flash("Không tìm thấy tài khoản.", "danger")
        return redirect(url_for("admin_users.user_list_page"))

    if int(target_user["user_id"]) == int(admin_user["user_id"]):
        flash("Không thể tự khóa tài khoản quản trị đang đăng nhập.", "danger")
        return redirect(url_for("admin_users.user_list_page"))

    if target_user["role"] == "admin":
        flash("Không thể khóa hoặc mở khóa tài khoản Admin tại đây.", "danger")
        return redirect(url_for("admin_users.user_list_page"))

    desired_raw = request.form.get("is_active", "").strip().lower()
    if desired_raw not in ("1", "0", "true", "false"):
        flash("Trạng thái tài khoản yêu cầu không hợp lệ.", "danger")
        return redirect(url_for("admin_users.user_list_page"))

    desired_active = desired_raw in ("1", "true")
    log_action = "unlock_user" if desired_active else "lock_user"

    try:
        set_user_status(user_id, desired_active)
    except auth_error as error:
        create_activity_log(
            admin_user["user_id"],
            log_action,
            "user",
            user_id,
            "failed",
            details=str(error),
        )
        flash(str(error), "danger")
        return redirect(url_for("admin_users.user_list_page"))

    status_label = "mở khóa" if desired_active else "khóa"
    create_activity_log(
        admin_user["user_id"],
        log_action,
        "user",
        user_id,
        "success",
        details=f"Đã {status_label} tài khoản {target_user['username']}",
    )
    flash(f"Đã {status_label} tài khoản '{target_user['username']}'.", "success")
    return redirect(url_for("admin_users.user_list_page"))
