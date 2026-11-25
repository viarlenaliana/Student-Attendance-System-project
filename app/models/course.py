from app.extensions import db


class Course(db.Model):
    __tablename__ = "courses"

    course_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    course_code = db.Column(
        db.String(20),
        nullable=False,
        unique=True
    )

    course_name = db.Column(
        db.String(100),
        nullable=False
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.department_id"),
        nullable=False
    )

    credits = db.Column(
        db.Integer,
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=True
    )