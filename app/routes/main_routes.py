from flask import Blueprint, render_template, session, redirect, url_for

from app.models.course import Course
from app.routes.auth import role_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@role_required("student")
def home():
    return render_template("student/dashboard.html")


@main_bp.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    return redirect(url_for("admin.users"))


@main_bp.route("/student/schedule")
@role_required("student")
def schedule():
    return render_template("student/schedule.html")


@main_bp.route("/student/history")
@role_required("student")
def attendance_history():
    return render_template("student/attendance_history.html")


@main_bp.route("/student/courses")
@role_required("student")
def courses():
    courses_list = (
        Course.query
        .order_by(Course.course_code.asc())
        .all()
    )

    return render_template(
        "student/courses.html",
        courses=courses_list
    )


@main_bp.route("/student/statistics")
@role_required("student")
def statistics():
    return render_template("student/statistics.html")