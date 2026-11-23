
from app.extensions import db


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    record_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    session_id = db.Column(
        db.Integer,
        db.ForeignKey("attendance_sessions.session_id"),
        nullable=False
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.student_id"),
        nullable=False
    )

    attendance_status = db.Column(
        db.String(20),
        nullable=False,
        default="ABSENT"
    )

    check_in_time = db.Column(
        db.DateTime,
        nullable=True
    )

    method_used = db.Column(
        db.String(30),
        nullable=True
    )

    note = db.Column(
        db.Text,
        nullable=True
    )

    __table_args__ = (
        db.UniqueConstraint(
            "session_id",
            "student_id",
            name="uq_session_student"
        ),
        db.CheckConstraint(
            "attendance_status IN "
            "('PRESENT', 'ABSENT', 'LATE', 'EXCUSED')",
            name="ck_attendance_record_status"
        ),
    )