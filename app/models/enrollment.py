from app.extensions import db


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    enrollment_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    section_id = db.Column(
        db.Integer,
        db.ForeignKey("course_sections.section_id"),
        nullable=False
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.student_id"),
        nullable=False
    )

    enrolled_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp()
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="ACTIVE"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "section_id",
            "student_id",
            name="uq_student_section"
        ),
    )