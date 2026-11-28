from datetime import date, datetime, time, timedelta
import io
import secrets

import qrcode
from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for
)
from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.lecturer import Lecturer
from app.models.student import Student
from app.models.course import Course
from app.models.course_section import CourseSection
from app.models.enrollment import Enrollment
from app.models.class_schedule import ClassSchedule
from app.models.attendance_session import AttendanceSession
from app.models.attendance_record import AttendanceRecord
from app.models.attendance_history import AttendanceRecordHistory
from app.models.attendance_complaint import AttendanceComplaint
from app.routes.auth import role_required

lecturer_bp = Blueprint("lecturer", __name__, url_prefix="/lecturer")
QR_REFRESH_SECONDS_DEFAULT = 30
QR_REFRESH_SECONDS_MIN = 5
QR_REFRESH_SECONDS_MAX = 300


def _lecturer_id():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or (user.role or "").lower() != "lecturer":
        abort(403)
    profile = db.session.get(Lecturer, user_id)
    if not profile:
        abort(403, description="Lecturer profile not found")
    return profile.lecturer_id


def _owned_section(section_id):
    return CourseSection.query.filter_by(
        section_id=section_id, lecturer_id=_lecturer_id()
    ).first_or_404()


def _owned_session(session_id):
    return AttendanceSession.query.filter_by(
        session_id=session_id, lecturer_id=_lecturer_id()
    ).first_or_404()


def _rotate_qr_if_needed(item):
    if item.status != "ACTIVE" or item.attendance_method not in ("QR_CODE", "QR_PASSWORD"):
        return
    now = datetime.now()
    if not item.qr_token or not item.qr_expired_at or now >= item.qr_expired_at:
        item.qr_token = secrets.token_urlsafe(24)
        refresh_seconds = item.qr_refresh_seconds or QR_REFRESH_SECONDS_DEFAULT
        item.qr_expired_at = now + timedelta(seconds=refresh_seconds)
        db.session.commit()


def _qr_png(token):
    qr = qrcode.QRCode(version=1, box_size=9, border=3)
    qr.add_data(token)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream


@lecturer_bp.route("/dashboard")
@role_required("lecturer")
def dashboard():
    lecturer_id = _lecturer_id()
    sections = CourseSection.query.filter_by(lecturer_id=lecturer_id).all()
    ids = [s.section_id for s in sections]
    students = Enrollment.query.filter(
        Enrollment.section_id.in_(ids), Enrollment.status == "ACTIVE"
    ).count() if ids else 0
    active_sessions = AttendanceSession.query.filter_by(
        lecturer_id=lecturer_id, status="ACTIVE"
    ).count()
    total_sessions = AttendanceSession.query.filter_by(lecturer_id=lecturer_id).count()
    return render_template(
        "lecturer/dashboard.html", sections=sections,
        section_count=len(sections), student_count=students,
        active_session_count=active_sessions, session_count=total_sessions
    )


@lecturer_bp.route("/sections")
@role_required("lecturer")
def sections():
    rows = db.session.query(CourseSection, Course).join(
        Course, Course.course_id == CourseSection.course_id
    ).filter(CourseSection.lecturer_id == _lecturer_id()).order_by(
        Course.course_code, CourseSection.section_code
    ).all()
    return render_template("lecturer/sections.html", rows=rows)


@lecturer_bp.route("/sections/<int:section_id>")
@role_required("lecturer")
def section_detail(section_id):
    section = _owned_section(section_id)
    course = db.session.get(Course, section.course_id)
    students = db.session.query(Student, User, Enrollment).join(
        User, User.user_id == Student.student_id
    ).join(Enrollment, Enrollment.student_id == Student.student_id).filter(
        Enrollment.section_id == section_id, Enrollment.status == "ACTIVE"
    ).order_by(User.full_name).all()
    schedules = ClassSchedule.query.filter_by(section_id=section_id).order_by(
        ClassSchedule.day_of_week, ClassSchedule.start_time
    ).all()
    sessions = AttendanceSession.query.filter_by(section_id=section_id).order_by(
        AttendanceSession.session_date.desc(), AttendanceSession.session_id.desc()
    ).all()
    return render_template(
        "lecturer/section_detail.html", section=section, course=course,
        students=students, schedules=schedules, sessions=sessions
    )


@lecturer_bp.route("/schedule")
@role_required("lecturer")
def schedule():
    rows = db.session.query(ClassSchedule, CourseSection, Course).join(
        CourseSection, CourseSection.section_id == ClassSchedule.section_id
    ).join(Course, Course.course_id == CourseSection.course_id).filter(
        CourseSection.lecturer_id == _lecturer_id()
    ).order_by(ClassSchedule.day_of_week, ClassSchedule.start_time).all()
    return render_template("lecturer/schedule.html", rows=rows)


@lecturer_bp.route("/sections/<int:section_id>/sessions/create", methods=["POST"])
@role_required("lecturer")
def create_session(section_id):
    section = _owned_section(section_id)
    method = (request.form.get("attendance_method") or "").strip().upper()
    aliases = {"QR": "QR_CODE", "QR+PASSWORD": "QR_PASSWORD", "QR_PASSWORD": "QR_PASSWORD"}
    method = aliases.get(method, method)
    allowed = {"QR_CODE", "PASSWORD", "QR_PASSWORD", "MANUAL"}
    if method not in allowed:
        flash("Please select a valid attendance method.", "danger")
        return redirect(url_for("lecturer.section_detail", section_id=section_id))

    today = date.today()
    schedule = ClassSchedule.query.filter(
        ClassSchedule.section_id == section_id,
        ClassSchedule.day_of_week == today.isoweekday(),
        ClassSchedule.effective_from <= today,
        ClassSchedule.effective_to >= today,
    ).order_by(ClassSchedule.start_time).first()
    try:
        start_raw = (request.form.get("start_time") or "").strip()
        end_raw = (request.form.get("end_time") or "").strip()
        start_value = time.fromisoformat(start_raw) if start_raw else (schedule.start_time if schedule else None)
        end_value = time.fromisoformat(end_raw) if end_raw else (schedule.end_time if schedule else None)
        if start_value and end_value and end_value <= start_value:
            raise ValueError("End time must be later than start time.")
        password = (request.form.get("attendance_password") or "").strip() or None
        if method in {"PASSWORD", "QR_PASSWORD"} and not password:
            raise ValueError("An attendance password is required for this method.")
        qr_token = secrets.token_urlsafe(24) if method in {"QR_CODE", "QR_PASSWORD"} else None
        try:
            qr_refresh_seconds = int(request.form.get("qr_refresh_seconds") or QR_REFRESH_SECONDS_DEFAULT)
        except (TypeError, ValueError):
            qr_refresh_seconds = QR_REFRESH_SECONDS_DEFAULT
        qr_refresh_seconds = max(QR_REFRESH_SECONDS_MIN, min(QR_REFRESH_SECONDS_MAX, qr_refresh_seconds))
        new_session = AttendanceSession(
            section_id=section_id,
            schedule_id=schedule.schedule_id if schedule else None,
            lecturer_id=_lecturer_id(),
            session_date=today,
            start_time=start_value,
            end_time=end_value,
            attendance_method=method,
            qr_token=qr_token,
            qr_expired_at=(datetime.now() + timedelta(seconds=qr_refresh_seconds)) if qr_token else None,
            qr_refresh_seconds=qr_refresh_seconds,
            attendance_password=password,
            allow_makeup=(request.form.get("allow_makeup") == "on"),
            status="ACTIVE",
        )
        db.session.add(new_session)
        db.session.flush()
        enrollments = Enrollment.query.filter_by(section_id=section_id, status="ACTIVE").all()
        for enrollment in enrollments:
            db.session.add(AttendanceRecord(
                session_id=new_session.session_id,
                student_id=enrollment.student_id,
                attendance_status="ABSENT"
            ))
        db.session.commit()
        flash("Attendance session opened successfully.", "success")
        return redirect(url_for("lecturer.session_detail", session_id=new_session.session_id))
    except Exception as exc:
        db.session.rollback()
        flash(f"Cannot open attendance session: {exc}", "danger")
        return redirect(url_for("lecturer.section_detail", section_id=section_id))


@lecturer_bp.route("/sessions/<int:session_id>")
@role_required("lecturer")
def session_detail(session_id):
    item = _owned_session(session_id)
    _rotate_qr_if_needed(item)
    section = db.session.get(CourseSection, item.section_id)
    course = db.session.get(Course, section.course_id) if section else None
    records = db.session.query(AttendanceRecord, User).join(
        Student, Student.student_id == AttendanceRecord.student_id
    ).join(User, User.user_id == Student.student_id).filter(
        AttendanceRecord.session_id == session_id
    ).order_by(User.full_name).all()
    counts = {status: sum(1 for record, _ in records if record.attendance_status == status)
              for status in ("PRESENT", "ABSENT", "LATE", "EXCUSED")}
    return render_template(
        "lecturer/session_detail.html", attendance_session=item,
        section=section, course=course, records=records, counts=counts
    )


@lecturer_bp.route("/sessions/<int:session_id>/qr.png")
@role_required("lecturer")
def qr_image(session_id):
    item = _owned_session(session_id)
    if item.status != "ACTIVE" or item.attendance_method not in {"QR_CODE", "QR_PASSWORD"}:
        abort(404)
    _rotate_qr_if_needed(item)
    response = send_file(_qr_png(item.qr_token), mimetype="image/png", download_name="uniattend-qr.png")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@lecturer_bp.route("/sessions/<int:session_id>/qr-status")
@role_required("lecturer")
def qr_status(session_id):
    item = _owned_session(session_id)
    if item.status != "ACTIVE" or item.attendance_method not in {"QR_CODE", "QR_PASSWORD"}:
        return jsonify({"active": False, "message": "Attendance session is closed."})
    _rotate_qr_if_needed(item)
    seconds = max(0, int((item.qr_expired_at - datetime.now()).total_seconds())) if item.qr_expired_at else 0
    return jsonify({
        "active": True, "remaining_seconds": seconds,
        "qr_image_url": url_for("lecturer.qr_image", session_id=session_id),
        "refresh_interval": item.qr_refresh_seconds or QR_REFRESH_SECONDS_DEFAULT
    })


@lecturer_bp.route("/sessions/<int:session_id>/records/<int:record_id>", methods=["POST"])
@role_required("lecturer")
def update_record(session_id, record_id):
    item = _owned_session(session_id)
    record = AttendanceRecord.query.filter_by(record_id=record_id, session_id=session_id).first_or_404()
    new_status = (request.form.get("attendance_status") or "").upper()
    if new_status not in {"PRESENT", "ABSENT", "LATE", "EXCUSED"}:
        abort(400)
    old_status = record.attendance_status
    reason = (request.form.get("note") or "").strip() or None
    if old_status != new_status:
        db.session.add(AttendanceRecordHistory(
            record_id=record.record_id, lecturer_id=item.lecturer_id,
            old_status=old_status, new_status=new_status, reason=reason
        ))
    record.attendance_status = new_status
    record.check_in_time = datetime.now() if new_status in {"PRESENT", "LATE"} else None
    record.method_used = "MANUAL"
    record.note = reason
    db.session.commit()
    flash("Attendance record updated.", "success")
    return redirect(url_for("lecturer.session_detail", session_id=session_id))


@lecturer_bp.route("/sessions/<int:session_id>/close", methods=["POST"])
@role_required("lecturer")
def close_session(session_id):
    item = _owned_session(session_id)
    item.status = "CLOSED"
    item.end_time = datetime.now().time()
    item.qr_token = None
    item.qr_expired_at = None
    db.session.commit()
    flash("Attendance session closed.", "success")
    return redirect(url_for("lecturer.session_detail", session_id=session_id))


@lecturer_bp.route("/complaints")
@role_required("lecturer")
def complaints():
    rows = db.session.query(AttendanceComplaint, AttendanceRecord, AttendanceSession,
                            Student, User, Course, CourseSection).join(
        AttendanceRecord, AttendanceComplaint.record_id == AttendanceRecord.record_id
    ).join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.session_id
    ).join(CourseSection, AttendanceSession.section_id == CourseSection.section_id
    ).join(Course, CourseSection.course_id == Course.course_id
    ).join(Student, AttendanceComplaint.student_id == Student.student_id
    ).join(User, User.user_id == Student.student_id).filter(
        AttendanceSession.lecturer_id == _lecturer_id()
    ).order_by(AttendanceComplaint.created_at.desc()).all()
    return render_template("lecturer/complaints.html", complaints=rows)


@lecturer_bp.route("/complaints/<int:complaint_id>/resolve", methods=["POST"])
@role_required("lecturer")
def resolve_complaint(complaint_id):
    complaint = db.session.query(AttendanceComplaint).join(
        AttendanceRecord, AttendanceComplaint.record_id == AttendanceRecord.record_id
    ).join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.session_id).filter(
        AttendanceComplaint.complaint_id == complaint_id,
        AttendanceSession.lecturer_id == _lecturer_id()
    ).first_or_404()
    if complaint.status != "PENDING":
        flash("This complaint has already been processed.", "warning")
        return redirect(url_for("lecturer.complaints"))
    decision = (request.form.get("decision") or "").upper()
    if decision not in {"APPROVED", "REJECTED"}:
        abort(400)
    complaint.status = decision
    complaint.response = (request.form.get("response") or "").strip() or None
    complaint.resolved_at = datetime.now()
    if decision == "APPROVED":
        record = db.session.get(AttendanceRecord, complaint.record_id)
        record.attendance_status = "PRESENT"
        record.check_in_time = datetime.now()
        record.method_used = "COMPLAINT"
    db.session.commit()
    flash("Complaint processed.", "success")
    return redirect(url_for("lecturer.complaints"))