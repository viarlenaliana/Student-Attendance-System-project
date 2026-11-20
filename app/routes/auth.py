"""Controller xử lý đăng nhập, đăng xuất, đổi mật khẩu, quên mật khẩu (OTP) và điều hướng theo vai trò."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from app.models.activity_log import create_activity_log
from app.models.notification import get_unread_notification_count, get_user_notifications
from app.models.user import (
    auth_error,
    change_password,
    check_user_permission,
    complete_verified_password_reset,
    create_password_otp,
    get_current_user,
    get_user_by_email,
    get_user_by_username,
    get_verified_otp_record,
    login_user,
    logout_user,
    verify_password_otp,
)

auth_bp = Blueprint("auth", __name__)


def _redirect_home_for_role(role):
    """Điều hướng trang mặc định sau đăng nhập theo vai trò."""
    if role == "admin":
        return redirect(url_for("admin_users.user_list_page"))
    return redirect(url_for("auth.dashboard"))


def login_required(view_function):
    """Yêu cầu người dùng đã đăng nhập và không còn trạng thái bắt buộc đổi mật khẩu."""
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            flash("Vui lòng đăng nhập để tiếp tục.", "warning")
            return redirect(url_for("auth.login_page"))

        allowed_when_must_change = ("auth.change_password_page", "auth.logout_action")
        if user.get("must_change_password") and request.endpoint not in allowed_when_must_change:
            flash("Bạn cần đổi mật khẩu mặc định ở lần đăng nhập đầu tiên trước khi tiếp tục.", "warning")
            return redirect(url_for("auth.change_password_page"))
        return view_function(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    """Kiểm tra đăng nhập và kiểm tra phân quyền theo vai trò ở phía server."""
    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user is None:
                flash("Vui lòng đăng nhập để tiếp tục.", "warning")
                return redirect(url_for("auth.login_page"))

            if user.get("must_change_password"):
                flash("Bạn cần đổi mật khẩu mặc định ở lần đăng nhập đầu tiên trước khi tiếp tục.", "warning")
                return redirect(url_for("auth.change_password_page"))

            if not check_user_permission(user["user_id"], allowed_roles):
                abort(403)
            return view_function(*args, **kwargs)

        return wrapper

    return decorator


@auth_bp.route("/")
def home():
    user = get_current_user()
    if user is not None:
        if user.get("must_change_password"):
            return redirect(url_for("auth.change_password_page"))
        return _redirect_home_for_role(user["role"])
    return render_template("home.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    current_user = get_current_user()
    if current_user is not None:
        if current_user.get("must_change_password"):
            return redirect(url_for("auth.change_password_page"))
        return _redirect_home_for_role(current_user["role"])

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            logged_in_user = login_user(username, password)
        except auth_error as error:
            existing_user = get_user_by_username(username)
            create_activity_log(
                existing_user["user_id"] if existing_user else None,
                "login",
                "auth",
                existing_user["user_id"] if existing_user else None,
                "failed",
                details="Đăng nhập thất bại",
                username=username or None,
            )
            flash(str(error), "danger")
            return render_template("login.html", entered_username=username), 401

        create_activity_log(
            logged_in_user["user_id"],
            "login",
            "user",
            logged_in_user["user_id"],
            "success",
            details=f"Đăng nhập thành công ({logged_in_user['role']})",
        )

        if logged_in_user.get("must_change_password"):
            flash("Đây là lần đăng nhập đầu tiên. Vui lòng đổi mật khẩu để bảo vệ tài khoản.", "warning")
            return redirect(url_for("auth.change_password_page"))

        flash(f"Xin chào {logged_in_user['full_name']}!", "success")
        return _redirect_home_for_role(logged_in_user["role"])

    return render_template("login.html", entered_username="")


@auth_bp.route("/logout", methods=["POST"])
def logout_action():
    user = get_current_user()
    if user is not None:
        create_activity_log(
            user["user_id"],
            "logout",
            "user",
            user["user_id"],
            "success",
            details="Đăng xuất khỏi hệ thống",
        )
    logout_user()
    flash("Bạn đã đăng xuất thành công.", "info")
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    recent_notifications = get_user_notifications(user["user_id"], limit=5)
    unread_count = get_unread_notification_count(user["user_id"])
    return render_template(
        "dashboard.html",
        current_user=user,
        recent_notifications=recent_notifications,
        unread_count=unread_count,
    )


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password_page():
    user = get_current_user()
    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not old_password or not new_password or not confirm_password:
            flash("Vui lòng nhập đầy đủ mật khẩu hiện tại, mật khẩu mới và xác nhận mật khẩu.", "danger")
            return render_template("auth/change_password.html", current_user=user), 400

        if new_password != confirm_password:
            flash("Mật khẩu mới và xác nhận mật khẩu không khớp.", "danger")
            return render_template("auth/change_password.html", current_user=user), 400

        try:
            change_password(user["user_id"], old_password, new_password)
        except auth_error as error:
            create_activity_log(
                user["user_id"],
                "change_password",
                "user",
                user["user_id"],
                "failed",
                details="Đổi mật khẩu thất bại",
            )
            flash(str(error), "danger")
            return render_template("auth/change_password.html", current_user=user), 400

        create_activity_log(
            user["user_id"],
            "change_password",
            "user",
            user["user_id"],
            "success",
            details="Đổi mật khẩu thành công",
        )
        flash("Đổi mật khẩu thành công.", "success")
        return _redirect_home_for_role(user["role"])

    return render_template("auth/change_password.html", current_user=user)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password_page():
    if get_current_user() is not None:
        return _redirect_home_for_role(get_current_user()["role"])

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        try:
            otp_result = create_password_otp(email)
        except auth_error as error:
            target_user = get_user_by_email(email) if email else None
            create_activity_log(
                target_user["user_id"] if target_user else None,
                "request_password_otp",
                "auth",
                target_user["user_id"] if target_user else None,
                "failed",
                details="Yêu cầu OTP thất bại",
                username=target_user["username"] if target_user else None,
            )
            flash(str(error), "danger")
            return render_template("auth/forgot_password.html", entered_email=email), 400

        target_user = get_user_by_email(otp_result["email"])
        create_activity_log(
            target_user["user_id"] if target_user else None,
            "request_password_otp",
            "user",
            target_user["user_id"] if target_user else None,
            "success",
            details=f"Đã tạo OTP khôi phục mật khẩu (email_status={otp_result['email_status']})",
        )
        session["otp_pending_email"] = otp_result["email"]
        session.pop("otp_verified_email", None)
        session.pop("otp_verified_id", None)

        if otp_result["email_status"] == "sent":
            flash(
                f"Mã OTP đã được gửi tới email {otp_result['email']}. "
                f"Mã có hiệu lực trong {otp_result['expiry_minutes']} phút.",
                "success",
            )
        else:
            flash(
                "Đã tạo yêu cầu OTP nhưng hệ thống chưa bật gửi email SMTP. "
                "Vui lòng kiểm tra cấu hình SMTP trong hướng dẫn cấu hình.",
                "warning",
            )
        return redirect(url_for("auth.verify_otp_page"))

    return render_template("auth/forgot_password.html", entered_email=session.get("otp_pending_email", ""))


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp_page():
    if get_current_user() is not None:
        return _redirect_home_for_role(get_current_user()["role"])

    pending_email = session.get("otp_pending_email", "")
    if request.method == "POST":
        email = request.form.get("email", pending_email).strip().lower()
        otp_code = request.form.get("otp", "").strip()

        if not email or not otp_code:
            flash("Vui lòng nhập đầy đủ email và mã OTP gồm 6 chữ số.", "danger")
            return render_template("auth/verify_otp.html", pending_email=email), 400

        is_valid = verify_password_otp(email, otp_code)
        target_user = get_user_by_email(email)
        if not is_valid:
            create_activity_log(
                target_user["user_id"] if target_user else None,
                "verify_password_otp",
                "auth",
                target_user["user_id"] if target_user else None,
                "failed",
                details="Xác minh OTP thất bại",
                username=target_user["username"] if target_user else None,
            )
            flash("Mã OTP không chính xác, đã hết hạn hoặc vượt quá số lần thử.", "danger")
            return render_template("auth/verify_otp.html", pending_email=email), 400

        verified_record = get_verified_otp_record(email)
        if verified_record is None:
            flash("Không thể xác nhận phiên OTP. Vui lòng yêu cầu mã mới.", "danger")
            return redirect(url_for("auth.forgot_password_page"))

        session["otp_pending_email"] = email
        session["otp_verified_email"] = email
        session["otp_verified_id"] = verified_record["otp_id"]

        create_activity_log(
            target_user["user_id"] if target_user else None,
            "verify_password_otp",
            "user",
            target_user["user_id"] if target_user else None,
            "success",
            details="Xác minh OTP thành công",
        )
        flash("Xác minh OTP thành công. Vui lòng đặt mật khẩu mới.", "success")
        return redirect(url_for("auth.reset_password_page"))

    return render_template("auth/verify_otp.html", pending_email=pending_email)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password_page():
    if get_current_user() is not None:
        return _redirect_home_for_role(get_current_user()["role"])

    verified_email = session.get("otp_verified_email")
    verified_otp_id = session.get("otp_verified_id")
    if not verified_email or not verified_otp_id or get_verified_otp_record(verified_email) is None:
        flash("Bạn cần xác minh OTP thành công trước khi đặt lại mật khẩu.", "warning")
        return redirect(url_for("auth.verify_otp_page"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not new_password or not confirm_password:
            flash("Vui lòng nhập đầy đủ mật khẩu mới và xác nhận mật khẩu.", "danger")
            return render_template("auth/reset_password.html", verified_email=verified_email), 400

        if new_password != confirm_password:
            flash("Mật khẩu mới và xác nhận mật khẩu không khớp.", "danger")
            return render_template("auth/reset_password.html", verified_email=verified_email), 400

        target_user = get_user_by_email(verified_email)
        try:
            complete_verified_password_reset(verified_email, verified_otp_id, new_password)
        except auth_error as error:
            create_activity_log(
                target_user["user_id"] if target_user else None,
                "reset_password",
                "user",
                target_user["user_id"] if target_user else None,
                "failed",
                details="Đặt lại mật khẩu thất bại",
            )
            flash(str(error), "danger")
            return render_template("auth/reset_password.html", verified_email=verified_email), 400

        create_activity_log(
            target_user["user_id"] if target_user else None,
            "reset_password",
            "user",
            target_user["user_id"] if target_user else None,
            "success",
            details="Đặt lại mật khẩu qua OTP thành công",
        )
        session.pop("otp_pending_email", None)
        session.pop("otp_verified_email", None)
        session.pop("otp_verified_id", None)
        flash("Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới.", "success")
        return redirect(url_for("auth.login_page"))

    return render_template("auth/reset_password.html", verified_email=verified_email)
