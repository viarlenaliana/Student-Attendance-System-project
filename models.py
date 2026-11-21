import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, 
    Enum, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"

class AttendanceMethod(str, enum.Enum):
    QR = "QR"
    PASSWORD = "PASSWORD"
    QR_PASSWORD = "QR_PASSWORD"
    MANUAL = "MANUAL"

class AppealStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    course_class_id = Column(String(64), nullable=False, index=True)
    student_id = Column(String(64), nullable=False, index=True)
    status = Column(Enum(AttendanceStatus), default=AttendanceStatus.ABSENT, nullable=False)
    method_used = Column(Enum(AttendanceMethod), nullable=True)
    check_in_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Ràng buộc cứng: Mỗi Student chỉ có tối đa 1 kết quả cho mỗi buổi
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student_attendance"),
    )

    audit_logs = relationship("AttendanceAuditLog", back_populates="record", cascade="all, delete-orphan")
    appeals = relationship("AttendanceAppeal", back_populates="record", cascade="all, delete-orphan")

class AttendanceAuditLog(Base):
    __tablename__ = "attendance_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("attendance_records.id"), nullable=False)
    changed_by = Column(String(64), nullable=False)  # ID của Lecturer thực hiện
    previous_status = Column(Enum(AttendanceStatus), nullable=False)
    new_status = Column(Enum(AttendanceStatus), nullable=False)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    record = relationship("AttendanceRecord", back_populates="audit_logs")

class AttendanceAttempt(Base):
    __tablename__ = "attendance_attempts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False)
    student_id = Column(String(64), nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    # Chỉ khóa nhập mật khẩu trong buổi hiện tại, không tác động bảng User
    is_locked_for_session = Column(Boolean, default=False, nullable=False)
    last_attempt_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student_attempt"),
    )

class AttendanceAppeal(Base):
    __tablename__ = "attendance_appeals"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("attendance_records.id"), nullable=False)
    student_id = Column(String(64), nullable=False, index=True)
    lecturer_id = Column(String(64), nullable=True)
    reason = Column(Text, nullable=False)
    evidence_url = Column(String(512), nullable=True)
    status = Column(Enum(AppealStatus), default=AppealStatus.PENDING, nullable=False)
    lecturer_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    record = relationship("AttendanceRecord", back_populates="appeals")