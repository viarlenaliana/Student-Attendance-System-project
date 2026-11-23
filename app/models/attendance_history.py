from app.extensions import db


class AttendanceRecordHistory(db.Model):
    __tablename__ = "attendance_record_history"

    history_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    record_id = db.Column(
        db.Integer,
        db.ForeignKey("attendance_records.record_id"),
        nullable=False
    )

    lecturer_id = db.Column(
        db.Integer,
        db.ForeignKey("lecturers.lecturer_id"),
        nullable=False
    )

    old_status = db.Column(
        db.String(20),
        nullable=False
    )

    new_status = db.Column(
        db.String(20),
        nullable=False
    )

    reason = db.Column(
        db.Text,
        nullable=True
    )

    changed_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    __table_args__ = (
        db.CheckConstraint(
            "old_status IN ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED')",
            name="ck_history_old_status"
        ),
        db.CheckConstraint(
            "new_status IN ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED')",
            name="ck_history_new_status"
        ),
    )