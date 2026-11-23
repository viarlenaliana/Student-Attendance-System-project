from functools import wraps

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, abort
)
from werkzeug.security import check_password_hash

from app.models.user import User

auth_bp = Blueprint("auth", __name__)

VALID_ROLES = {"admin", "lecturer", "student"}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    allowed = {role.lower() for role in allowed_roles}

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            role = (session.get("role") or "").lower()

            if role not in allowed:
                abort(403)

            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_role_dashboard(role):
    role = (role or "").lower()

    if role == "admin":
        return url_for("admin.users")

    if role == "lecturer":
        return url_for("lecturer.dashboard")

    if role == "student":
        return url_for("main.home")

    return url_for("auth.login")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if session.get("user_id"):
        return redirect(
            get_role_dashboard(session.get("role"))
        )

    if request.method == "POST":

        username = (
            request.form.get("account_id")
            or request.form.get("username")
            or ""
        ).strip()

        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        password_ok = False

        if user and user.password_hash:
            try:
                password_ok = check_password_hash(
                    user.password_hash, password
                )
            except (TypeError, ValueError):
                password_ok = False

        active = (
            user is not None
            and user.is_active
            and (user.status or "").upper() == "ACTIVE"
        )

        role = (
            (user.role or "").strip().lower()
            if user else ""
        )

        if password_ok and active and role in VALID_ROLES:

            session.clear()
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["role"] = role

            flash("Đăng nhập thành công!", "success")

            return redirect(get_role_dashboard(role))

        flash(
            "Tên đăng nhập hoặc mật khẩu không chính xác, "
            "hoặc tài khoản đã bị khóa.",
            "danger"
        )

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất.", "success")
    return redirect(url_for("auth.login"))