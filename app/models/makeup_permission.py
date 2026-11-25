from app.extensions import db


class MakeupAttendancePermission(db.Model):
    __tablename__ = "makeup_attendance_permissions"

    permission_id = db.Column(
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

    approved_by = db.Column(
        db.Integer,
        db.ForeignKey("lecturers.lecturer_id"),
        nullable=False
    )

    granted_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="ACTIVE"
    )

    reason = db.Column(
        db.Text,
        nullable=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('ACTIVE', 'USED', 'EXPIRED', 'REVOKED')",
            name="ck_makeup_permission_status"
        ),
        db.UniqueConstraint(
            "session_id",
            "student_id",
            name="uq_makeup_session_student"
        ),
        db.CheckConstraint(
            "expires_at > granted_at",
            name="ck_makeup_permission_expiry"
        ),
    )