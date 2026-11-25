import os
import time
import secrets
import hashlib
import hmac
import smtplib

from email.message import EmailMessage
from functools import wraps

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, current_app
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from app.extensions import db
from app.models.user import User
from app.models.student import Student
from app.models.lecturer import Lecturer


auth_bp = Blueprint("auth", __name__)



# OTP CONFIGURATION


OTP_EXPIRE_SECONDS = 300       
OTP_RESEND_SECONDS = 60         
OTP_MAX_ATTEMPTS = 5


def clear_otp_session():
    keys = [
        "reset_email",
        "reset_otp_hash",
        "reset_otp_expiry",
        "reset_otp_attempts",
        "reset_otp_last_sent",
        "reset_otp_verified"
    ]

    for key in keys:
        session.pop(key, None)


def hash_otp(otp):
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def send_otp_email(receiver_email, otp):
    mail_username = os.getenv("MAIL_USERNAME")
    mail_password = os.getenv("MAIL_PASSWORD")
    mail_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    mail_port = int(os.getenv("MAIL_PORT", "587"))
    mail_sender = os.getenv("MAIL_DEFAULT_SENDER", mail_username)

    if not mail_username or not mail_password or not mail_sender:
        raise RuntimeError("Email configuration is missing.")

    message = EmailMessage()
    message["Subject"] = "UniAttend - Password Reset OTP"
    message["From"] = mail_sender
    message["To"] = receiver_email

    message.set_content(
        f"""
Hello,

We received a request to reset your UniAttend password.

Your verification code is:

{otp}

This code expires in 5 minutes.

If you did not request a password reset, please ignore this email.

UniAttend System
"""
    )

    with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(mail_username, mail_password)
        server.send_message(message)



# LOGIN

def find_login_user(account_id):
    """Admin: User.user_id; Student/Lecturer: profile code."""
    if not account_id:
        return None

    if account_id.isdigit():
        admin_user = db.session.get(User, int(account_id))
        if admin_user and (admin_user.role or "").strip().lower() == "admin":
            return admin_user

    student = Student.query.filter_by(student_code=account_id).first()
    if student:
        user = db.session.get(User, student.student_id)
        if user and (user.role or "").strip().lower() == "student":
            return user

    lecturer = Lecturer.query.filter_by(lecturer_code=account_id).first()
    if lecturer:
        user = db.session.get(User, lecturer.lecturer_id)
        if user and (user.role or "").strip().lower() == "lecturer":
            return user

    # Keep compatibility with the previous Admin username during transition.
    return User.query.filter_by(username=account_id, role="admin").first()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        account_id = (request.form.get("login_id") or request.form.get("username") or "").strip()
        password = request.form.get("password", "")
        user = find_login_user(account_id)

        valid_password = user is not None and check_password_hash(user.password_hash, password)
        valid_status = user is not None and bool(user.is_active) and user.status == "ACTIVE"

        if valid_password and valid_status:
            session.clear()
            session["user_id"] = user.user_id
            session["username"] = user.username
            session["full_name"] = user.full_name
            session["role"] = user.role.strip().lower()
            flash("Đăng nhập thành công!", "success")

            if getattr(user, "must_change_password", False):
                return redirect(url_for("auth.change_password"))
            if session["role"] == "admin":
                return redirect(url_for("admin.dashboard"))
            if session["role"] == "lecturer":
                return redirect(url_for("lecturer.dashboard"))
            return redirect(url_for("main.home"))

        flash("Mã tài khoản hoặc mật khẩu không chính xác, hoặc tài khoản đã bị khóa.", "danger")

    return render_template("login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = db.session.get(User, session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not check_password_hash(user.password_hash, current_password):
            flash("Mật khẩu hiện tại không đúng.", "danger")
        elif len(new_password) < 8:
            flash("Mật khẩu mới phải có ít nhất 8 ký tự.", "danger")
        elif new_password != confirm_password:
            flash("Mật khẩu xác nhận không khớp.", "danger")
        else:
            user.password_hash = generate_password_hash(new_password)
            user.must_change_password = False
            db.session.commit()
            flash("Đổi mật khẩu thành công.", "success")
            role = (user.role or "").lower()
            if role == "admin":
                return redirect(url_for("admin.dashboard"))
            if role == "lecturer":
                return redirect(url_for("lecturer.dashboard"))
            return redirect(url_for("main.home"))
    return render_template("change_password.html")



# FORGOT PASSWORD - SEND OTP


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Vui lòng nhập email.", "danger")
            return render_template("forgot_password.html")

        current_time = int(time.time())

        last_sent = session.get("reset_otp_last_sent", 0)

        if current_time - last_sent < OTP_RESEND_SECONDS:
            flash(
                "Vui lòng chờ trước khi yêu cầu gửi mã OTP mới.",
                "danger"
            )
            return render_template("forgot_password.html")

        user = User.query.filter(
            User.email.ilike(email)
        ).first()

        # Không tiết lộ email có tồn tại trong hệ thống hay không.
        if user:

            otp = f"{secrets.randbelow(1000000):06d}"

            try:
                send_otp_email(user.email, otp)

                session["reset_email"] = user.email
                session["reset_otp_hash"] = hash_otp(otp)
                session["reset_otp_expiry"] = (
                    current_time + OTP_EXPIRE_SECONDS
                )
                session["reset_otp_attempts"] = 0
                session["reset_otp_last_sent"] = current_time
                session["reset_otp_verified"] = False

            except Exception:
                current_app.logger.exception(
                    "Failed to send password reset email."
                )

                clear_otp_session()

                flash(
                    "Không thể gửi email lúc này. "
                    "Vui lòng kiểm tra cấu hình email hoặc thử lại sau.",
                    "danger"
                )

                return render_template("forgot_password.html")

        else:
            # Vẫn trả thông báo giống nhau để tránh dò email.
            session["reset_otp_last_sent"] = current_time

        flash(
            "Nếu email đã đăng ký trong hệ thống, "
            "mã OTP sẽ được gửi đến email đó.",
            "success"
        )

        return redirect(url_for("auth.verify_otp"))

    return render_template("forgot_password.html")



# VERIFY OTP


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():

    if not session.get("reset_email"):
        flash("Vui lòng yêu cầu mã OTP trước.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":

        if session.get("reset_otp_verified"):
            return redirect(url_for("auth.reset_password"))

        current_time = int(time.time())

        expiry = session.get("reset_otp_expiry", 0)

        if current_time > expiry:
            clear_otp_session()

            flash(
                "Mã OTP đã hết hạn. Vui lòng yêu cầu mã mới.",
                "danger"
            )

            return redirect(url_for("auth.forgot_password"))

        attempts = session.get("reset_otp_attempts", 0)

        if attempts >= OTP_MAX_ATTEMPTS:
            clear_otp_session()

            flash(
                "Bạn đã nhập sai OTP quá số lần cho phép. "
                "Vui lòng yêu cầu mã mới.",
                "danger"
            )

            return redirect(url_for("auth.forgot_password"))

        otp = request.form.get("otp", "").strip()

        if not otp.isdigit() or len(otp) != 6:

            session["reset_otp_attempts"] = attempts + 1

            flash("Mã OTP phải gồm 6 chữ số.", "danger")

            return render_template("verify_otp.html")

        submitted_hash = hash_otp(otp)
        saved_hash = session.get("reset_otp_hash", "")

        if not hmac.compare_digest(submitted_hash, saved_hash):

            session["reset_otp_attempts"] = attempts + 1

            remaining = OTP_MAX_ATTEMPTS - attempts - 1

            flash(
                f"Mã OTP không chính xác. Còn {remaining} lần thử.",
                "danger"
            )

            return render_template("verify_otp.html")

        session["reset_otp_verified"] = True

        flash("Xác minh OTP thành công.", "success")

        return redirect(url_for("auth.reset_password"))

    return render_template("verify_otp.html")



# RESET PASSWORD


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():

    if not session.get("reset_otp_verified"):
        flash("Vui lòng xác minh OTP trước.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if time.time() > session.get("reset_otp_expiry", 0):
        clear_otp_session()

        flash(
            "Phiên xác minh đã hết hạn. Vui lòng thực hiện lại.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash(
                "Mật khẩu mới phải có ít nhất 8 ký tự.",
                "danger"
            )
            return render_template("reset_password.html")

        if password != confirm_password:
            flash(
                "Mật khẩu xác nhận không khớp.",
                "danger"
            )
            return render_template("reset_password.html")

        email = session.get("reset_email")

        user = User.query.filter_by(email=email).first()

        if not user:
            clear_otp_session()

            flash(
                "Không tìm thấy tài khoản. Vui lòng thử lại.",
                "danger"
            )

            return redirect(url_for("auth.forgot_password"))

        user.password_hash = generate_password_hash(password)
        user.must_change_password = False

        from app.extensions import db

        db.session.commit()

        clear_otp_session()

        flash(
            "Đổi mật khẩu thành công. Vui lòng đăng nhập lại.",
            "success"
        )

        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")



# LOGOUT


@auth_bp.route("/logout")
def logout():

    session.clear()

    flash("Đã đăng xuất.", "success")

    return redirect(url_for("auth.login"))



# LOGIN REQUIRED

def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("auth.login"))

        return view(*args, **kwargs)

    return wrapped

# ROLE REQUIRED
def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            role = (session.get("role") or "").strip().lower()
            allowed = {str(item).lower() for item in allowed_roles}
            if role not in allowed:
                flash("Bạn không có quyền truy cập chức năng này.", "danger")
                if role == "admin":
                    return redirect(url_for("admin.dashboard"))
                if role == "lecturer":
                    return redirect(url_for("lecturer.dashboard"))
                return redirect(url_for("main.home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator