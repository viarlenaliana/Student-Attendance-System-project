from app.extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    department_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    department_code = db.Column(
        db.String(20),
        nullable=False,
        unique=True
    )

    department_name = db.Column(
        db.String(100),
        nullable=False,
        unique=True
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    def __repr__(self):
        return f"<Department {self.department_name}>"