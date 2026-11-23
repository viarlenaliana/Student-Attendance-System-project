from app.extensions import db


class AttendanceComplaint(db.Model):
    __tablename__ = "attendance_complaints"

    complaint_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    record_id = db.Column(
        db.Integer,
        db.ForeignKey("attendance_records.record_id"),
        nullable=False
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.student_id"),
        nullable=False
    )

    content = db.Column(
        db.Text,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING"
    )

    response = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    resolved_at = db.Column(
        db.DateTime,
        nullable=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_complaint_status"
        ),
        db.CheckConstraint(
            "LENGTH(TRIM(content)) > 0",
            name="ck_complaint_content"
        ),
    )