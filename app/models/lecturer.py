from app.extensions import db


class Lecturer(db.Model):
    __tablename__ = "lecturers"

    lecturer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        primary_key=True
    )

    lecturer_code = db.Column(
        db.String(20),
        nullable=False,
        unique=True
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.department_id"),
        nullable=False
    )