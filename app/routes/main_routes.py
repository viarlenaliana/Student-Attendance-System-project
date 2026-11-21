from flask import Blueprint, render_template
from app.models.course import Course
from app.models.department import Department

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("student/dashboard.html")


@main_bp.route("/student/schedule")
def schedule():
    return render_template("student/schedule.html")


@main_bp.route("/student/history")
def attendance_history():
    return render_template("student/attendance_history.html")


@main_bp.route("/student/courses")
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
def statistics():
    return render_template("student/statistics.html")