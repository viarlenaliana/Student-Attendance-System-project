from app.extensions import db


class Student(db.Model):
    __tablename__ = "students"

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        primary_key=True
    )

    student_code = db.Column(
        db.String(20),
        nullable=False,
        unique=True
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.department_id"),
        nullable=False
    )

    enrollment_year = db.Column(
        db.Integer,
        nullable=True
    )