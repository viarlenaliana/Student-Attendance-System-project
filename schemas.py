from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from models import AttendanceStatus, AttendanceMethod, AppealStatus

class CheckInRequest(BaseModel):
    session_id: str
    qr_token: Optional[str] = None
    password: Optional[str] = None

class CheckInResponse(BaseModel):
    success: bool
    message: str
    record_id: int
    status: AttendanceStatus
    check_in_at: datetime

class LecturerUpdateAttendanceRequest(BaseModel):
    status: AttendanceStatus
    reason: Optional[str] = None

class ManualRollCallItem(BaseModel):
    student_id: str
    status: AttendanceStatus

class ManualRollCallRequest(BaseModel):
    records: List[ManualRollCallItem]

class CreateAppealRequest(BaseModel):
    record_id: int
    reason: str = Field(..., min_length=5)
    evidence_url: Optional[str] = None

class ResolveAppealRequest(BaseModel):
    status: AppealStatus  # IN_PROGRESS, ACCEPTED, REJECTED
    lecturer_response: Optional[str] = None
    new_attendance_status: Optional[AttendanceStatus] = None  # Dùng khi ACCEPTED (vd: PRESENT hoặc EXCUSED)