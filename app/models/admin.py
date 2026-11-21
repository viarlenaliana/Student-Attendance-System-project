from app.extensions import db


class Admin(db.Model):
    __tablename__ = "admins"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        primary_key=True
    )