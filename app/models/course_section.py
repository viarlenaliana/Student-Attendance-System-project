from app.extensions import db


class CourseSection(db.Model):
    __tablename__ = "course_sections"

    section_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    course_id = db.Column(
        db.Integer,
        db.ForeignKey("courses.course_id"),
        nullable=False
    )

    lecturer_id = db.Column(
        db.Integer,
        db.ForeignKey("lecturers.lecturer_id"),
        nullable=False
    )

    section_code = db.Column(
        db.String(30),
        nullable=False
    )

    semester = db.Column(
        db.String(30),
        nullable=False
    )

    academic_year = db.Column(
        db.String(20),
        nullable=False
    )

    max_students = db.Column(
        db.Integer,
        nullable=True
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="ACTIVE"
    )