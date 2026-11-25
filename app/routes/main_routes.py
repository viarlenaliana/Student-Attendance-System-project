from datetime import date, datetime
import hmac

from flask import (
    Blueprint, render_template, session, redirect, url_for, flash,
    request, jsonify, current_app, abort
)
from sqlalchemy import func, case

from app.extensions import db
from app.models.user import User
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.course_section import CourseSection
from app.models.course import Course
from app.models.department import Department
from app.models.class_schedule import ClassSchedule
from app.models.attendance_session import AttendanceSession
from app.models.attendance_record import AttendanceRecord
from app.models.attendance_complaint import AttendanceComplaint
from app.routes.auth import role_required

main_bp = Blueprint("main", __name__)


def current_student_id():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if not user or (user.role or "").lower() != "student":
        return None
    student = db.session.get(Student, user_id)
    return student.student_id if student else None


def _student_or_redirect():
    student_id = current_student_id()
    if student_id is None:
        flash("Student profile not found for this account.", "danger")
        return None
    return student_id


def _record_checkin(item, student_id, method):
    enrollment = Enrollment.query.filter_by(
        section_id=item.section_id, student_id=student_id, status="ACTIVE"
    ).first()
    if not enrollment:
        return False, "You are not actively enrolled in this class.", 403
    record = AttendanceRecord.query.filter_by(
        session_id=item.session_id, student_id=student_id
    ).first()
    if not record:
        return False, "Attendance record not found. Ask your lecturer to refresh the session.", 404
    if record.attendance_status in {"PRESENT", "LATE"}:
        return True, "Your attendance has already been recorded.", 200
    if item.status != "ACTIVE":
        return False, "This attendance session is closed.", 400
    record.attendance_status = "PRESENT"
    record.check_in_time = datetime.now()
    record.method_used = method
    db.session.commit()
    return True, "Attendance recorded successfully.", 200


@main_bp.route("/")
@role_required("student")
def home():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    course_count = db.session.query(func.count(func.distinct(CourseSection.course_id))).join(
        Enrollment, Enrollment.section_id == CourseSection.section_id
    ).filter(Enrollment.student_id == student_id, Enrollment.status == "ACTIVE").scalar() or 0
    total, attended, absent = db.session.query(
        func.count(AttendanceRecord.record_id),
        func.sum(case((AttendanceRecord.attendance_status.in_(["PRESENT", "LATE"]), 1), else_=0)),
        func.sum(case((AttendanceRecord.attendance_status == "ABSENT", 1), else_=0)),
    ).filter(AttendanceRecord.student_id == student_id).one()
    total, attended, absent = int(total or 0), int(attended or 0), int(absent or 0)
    return render_template(
        "student/dashboard.html", course_count=course_count,
        attended_count=attended, absent_count=absent,
        attendance_rate=round(attended * 100 / total) if total else 0,
        total_sessions=total
    )


@main_bp.route("/student/schedule")
@role_required("student")
def schedule():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    today = date.today()
    rows = db.session.query(ClassSchedule, CourseSection, Course, User).join(
        CourseSection, ClassSchedule.section_id == CourseSection.section_id
    ).join(Enrollment, Enrollment.section_id == CourseSection.section_id).join(
        Course, CourseSection.course_id == Course.course_id
    ).join(User, CourseSection.lecturer_id == User.user_id).filter(
        Enrollment.student_id == student_id,
        Enrollment.status == "ACTIVE",
        CourseSection.status == "ACTIVE",
        ClassSchedule.effective_from <= today,
        ClassSchedule.effective_to >= today,
    ).order_by(ClassSchedule.day_of_week, ClassSchedule.start_time).all()
    return render_template("student/schedule.html", schedule_rows=rows)


@main_bp.route("/student/courses")
@role_required("student")
def courses():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    rows = db.session.query(Enrollment, CourseSection, Course, Department, User).join(
        CourseSection, Enrollment.section_id == CourseSection.section_id
    ).join(Course, CourseSection.course_id == Course.course_id).outerjoin(
        Department, Course.department_id == Department.department_id
    ).join(User, CourseSection.lecturer_id == User.user_id).filter(
        Enrollment.student_id == student_id,
        Enrollment.status == "ACTIVE",
        CourseSection.status == "ACTIVE"
    ).order_by(Course.course_code, CourseSection.section_code).all()
    return render_template("student/courses.html", enrolled_courses=rows)


@main_bp.route("/student/history")
@role_required("student")
def attendance_history():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    rows = db.session.query(AttendanceRecord, AttendanceSession, Course, CourseSection).join(
        AttendanceSession, AttendanceRecord.session_id == AttendanceSession.session_id
    ).join(CourseSection, AttendanceSession.section_id == CourseSection.section_id).join(
        Course, CourseSection.course_id == Course.course_id
    ).filter(AttendanceRecord.student_id == student_id).order_by(
        AttendanceSession.session_date.desc(), AttendanceSession.session_id.desc()
    ).all()
    return render_template("student/attendance_history.html", records=rows)


@main_bp.route("/student/statistics")
@role_required("student")
def statistics():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    rows = db.session.query(
        Course.course_code, Course.course_name,
        func.count(AttendanceRecord.record_id).label("total"),
        func.sum(case((AttendanceRecord.attendance_status.in_(["PRESENT", "LATE"]), 1), else_=0)).label("attended"),
        func.sum(case((AttendanceRecord.attendance_status == "ABSENT", 1), else_=0)).label("absent"),
    ).join(CourseSection, Course.course_id == CourseSection.course_id).join(
        AttendanceSession, AttendanceSession.section_id == CourseSection.section_id
    ).join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.session_id).filter(
        AttendanceRecord.student_id == student_id
    ).group_by(Course.course_id, Course.course_code, Course.course_name).order_by(Course.course_code).all()
    total = sum(int(row.total or 0) for row in rows)
    attended = sum(int(row.attended or 0) for row in rows)
    absent = sum(int(row.absent or 0) for row in rows)
    return render_template(
        "student/statistics.html", stats=rows, total=total,
        attended=attended, absent=absent,
        attendance_rate=round(attended * 100 / total) if total else 0
    )


@main_bp.route("/student/attendance")
@role_required("student")
def attendance():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    active_sessions = db.session.query(AttendanceSession, CourseSection, Course).join(
        CourseSection, AttendanceSession.section_id == CourseSection.section_id
    ).join(Course, CourseSection.course_id == Course.course_id).join(
        Enrollment, Enrollment.section_id == CourseSection.section_id
    ).filter(
        Enrollment.student_id == student_id,
        Enrollment.status == "ACTIVE",
        AttendanceSession.status == "ACTIVE"
    ).order_by(AttendanceSession.session_date.desc()).all()
    return render_template("student/attendance.html", active_sessions=active_sessions)


@main_bp.route("/student/attendance/<int:session_id>/checkin", methods=["POST"])
@role_required("student")
def password_checkin(session_id):
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    item = AttendanceSession.query.get_or_404(session_id)
    if item.attendance_method != "PASSWORD":
        flash("This session does not use password attendance.", "danger")
        return redirect(url_for("main.attendance"))
    supplied = (request.form.get("attendance_password") or "").strip()
    expected = item.attendance_password or ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        flash("Attendance password is incorrect.", "danger")
        return redirect(url_for("main.attendance"))
    ok, message, status = _record_checkin(item, student_id, "PASSWORD")
    flash(message, "success" if ok else "danger")
    return redirect(url_for("main.attendance"))


@main_bp.route("/student/scan")
@role_required("student")
def student_scan_page():
    return render_template("student/scan_qr.html")


@main_bp.route("/student/scan-qr", methods=["POST"])
@role_required("student")
def scan_qr_attendance():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = (data.get("password") or "").strip()
    if not token:
        return jsonify(success=False, message="QR token is missing."), 400
    student_id = _student_or_redirect()
    if student_id is None:
        return jsonify(success=False, message="Student profile not found."), 404
    item = AttendanceSession.query.filter_by(qr_token=token).first()
    if not item or item.status != "ACTIVE":
        return jsonify(success=False, message="QR code is invalid or the session is closed."), 400
    if item.attendance_method not in {"QR_CODE", "QR_PASSWORD"}:
        return jsonify(success=False, message="QR attendance is not enabled for this session."), 400
    if not item.qr_expired_at or datetime.now() >= item.qr_expired_at:
        return jsonify(success=False, message="QR code expired. Please scan the latest code."), 400
    if item.attendance_method == "QR_PASSWORD":
        if not password:
            return jsonify(success=False, requires_password=True, message="Enter the attendance password."), 200
        if not hmac.compare_digest(password, item.attendance_password or ""):
            return jsonify(success=False, message="Attendance password is incorrect."), 400
    ok, message, status = _record_checkin(item, student_id, "QR_PASSWORD" if item.attendance_method == "QR_PASSWORD" else "QR_CODE")
    return jsonify(success=ok, message=message), status


@main_bp.route("/student/complaints")
@role_required("student")
def student_complaints():
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    rows = db.session.query(AttendanceComplaint, AttendanceRecord, AttendanceSession, Course, CourseSection).join(
        AttendanceRecord, AttendanceComplaint.record_id == AttendanceRecord.record_id
    ).join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.session_id).join(
        CourseSection, AttendanceSession.section_id == CourseSection.section_id
    ).join(Course, CourseSection.course_id == Course.course_id).filter(
        AttendanceComplaint.student_id == student_id
    ).order_by(AttendanceComplaint.created_at.desc()).all()
    return render_template("student/complaints.html", complaints=rows)


@main_bp.route("/student/complaints/create/<int:record_id>", methods=["GET", "POST"])
@role_required("student")
def create_complaint(record_id):
    student_id = _student_or_redirect()
    if student_id is None:
        return redirect(url_for("auth.logout"))
    record = AttendanceRecord.query.filter_by(record_id=record_id, student_id=student_id).first_or_404()
    if record.attendance_status not in {"ABSENT", "EXCUSED"}:
        flash("A complaint can only be submitted for an absent or excused record.", "warning")
        return redirect(url_for("main.attendance_history"))
    existing = AttendanceComplaint.query.filter_by(record_id=record_id, student_id=student_id).filter(
        AttendanceComplaint.status == "PENDING"
    ).first()
    if existing:
        flash("A pending complaint already exists for this record.", "warning")
        return redirect(url_for("main.attendance_history"))
    if request.method == "POST":
        content = (request.form.get("content") or "").strip()
        if not content:
            flash("Please enter the reason for your complaint.", "danger")
        else:
            db.session.add(AttendanceComplaint(record_id=record_id, student_id=student_id, content=content))
            db.session.commit()
            flash("Complaint submitted to your lecturer.", "success")
            return redirect(url_for("main.student_complaints"))
    return render_template("student/complaint_create.html", record=record)