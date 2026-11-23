from app.extensions import db


class ClassSchedule(db.Model):
    __tablename__ = "class_schedules"

    schedule_id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True
    )

    section_id = db.Column(
        db.Integer,
        db.ForeignKey("course_sections.section_id"),
        nullable=False
    )

    day_of_week = db.Column(
        db.Integer,
        nullable=False
    )

    start_time = db.Column(
        db.Time,
        nullable=False
    )

    end_time = db.Column(
        db.Time,
        nullable=False
    )

    room = db.Column(
        db.String(50),
        nullable=True
    )

    effective_from = db.Column(
        db.Date,
        nullable=False
    )

    effective_to = db.Column(
        db.Date,
        nullable=False
    )

    __table_args__ = (
        db.CheckConstraint(
            "day_of_week BETWEEN 1 AND 7",
            name="ck_schedule_day"
        ),
        db.CheckConstraint(
            "start_time < end_time",
            name="ck_schedule_time"
        ),
       db.CheckConstraint(
            "effective_from <= effective_to",
            name="ck_schedule_date"
        ),
    )