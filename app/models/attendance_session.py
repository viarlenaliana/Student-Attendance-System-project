from app.extensions import db


class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"

    session_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    section_id = db.Column(
        db.Integer,
        db.ForeignKey("course_sections.section_id"),
        nullable=False
    )

    schedule_id = db.Column(
        db.Integer,
        db.ForeignKey("class_schedules.schedule_id"),
        nullable=True
    )

    lecturer_id = db.Column(
        db.Integer,
        db.ForeignKey("lecturers.lecturer_id"),
        nullable=False
    )

    session_date = db.Column(
        db.Date,
        nullable=False
    )

    start_time = db.Column(
        db.Time,
        nullable=True
    )

    end_time = db.Column(
        db.Time,
        nullable=True
    )

    attendance_method = db.Column(
        db.String(30),
        nullable=False
    )

    qr_token = db.Column(
        db.String(255),
        nullable=True
    )

    qr_expired_at = db.Column(
        db.DateTime,
        nullable=True
    )

    attendance_password = db.Column(
        db.String(255),
        nullable=True
    )

    allow_makeup = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="SCHEDULED"
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    __table_args__ = (
        db.CheckConstraint(
            "attendance_method IN "
            "('QR_CODE', 'PASSWORD', 'QR_PASSWORD', 'MANUAL')",
            name="ck_attendance_method"
        ),
        db.CheckConstraint(
            "status IN "
            "('SCHEDULED', 'ACTIVE', 'CLOSED', 'CANCELLED')",
            name="ck_attendance_status"
        ),
    )