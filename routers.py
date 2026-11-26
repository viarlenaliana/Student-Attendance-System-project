from typing import Optional
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models import AttendanceRecord, AttendanceAuditLog, AttendanceAppeal
from schemas import (
    CheckInRequest, CheckInResponse,
    LecturerUpdateAttendanceRequest, ManualRollCallRequest,
    CreateAppealRequest, ResolveAppealRequest
)
from services import AttendanceService

router = APIRouter(prefix="/api/v1", tags=["Attendance Management"])

# Dependency giả lập lấy DB & User hiện tại từ Token
def get_db():
    pass

def get_current_user_id(x_user_id: str = Header(...)) -> str:
    return x_user_id

# ==================== STUDENT ENDPOINTS ====================

@router.post("/student/attendance/check-in", response_model=CheckInResponse)
def student_check_in(
    payload: CheckInRequest,
    student_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    record = AttendanceService.student_check_in(
        db=db,
        student_id=student_id,
        session_id=payload.session_id,
        qr_token=payload.qr_token,
        password=payload.password
    )
    return CheckInResponse(
        success=True,
        message="Điểm danh thành công",
        record_id=record.id,
        status=record.status,
        check_in_at=record.check_in_at
    )

@router.post("/student/appeals")
def submit_appeal(
    payload: CreateAppealRequest,
    student_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return AttendanceService.create_appeal(
        db, student_id, payload.record_id, payload.reason, payload.evidence_url
    )

@router.get("/student/appeals")
def list_my_appeals(
    student_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return db.query(AttendanceAppeal).filter_by(student_id=student_id).all()

# ==================== LECTURER ENDPOINTS ====================

@router.get("/lecturer/sessions/{session_id}/records")
def get_session_attendance_list(session_id: str, db: Session = Depends(get_db)):
    return db.query(AttendanceRecord).filter_by(session_id=session_id).all()

@router.patch("/lecturer/attendance/{record_id}")
def update_attendance_record(
    record_id: int,
    payload: LecturerUpdateAttendanceRequest,
    lecturer_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return AttendanceService.lecturer_update_status(
        db, lecturer_id, record_id, payload.status, payload.reason
    )

@router.get("/lecturer/attendance/{record_id}/history")
def get_attendance_audit_history(record_id: int, db: Session = Depends(get_db)):
    return db.query(AttendanceAuditLog).filter_by(record_id=record_id).order_by(
        AttendanceAuditLog.changed_at.desc()
    ).all()

@router.post("/lecturer/sessions/{session_id}/manual-rollcall")
def manual_roll_call(
    session_id: str,
    payload: ManualRollCallRequest,
    lecturer_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    items = [item.model_dump() for item in payload.records]
    return AttendanceService.manual_roll_call(db, lecturer_id, session_id, items)

@router.patch("/lecturer/appeals/{appeal_id}")
def handle_appeal(
    appeal_id: int,
    payload: ResolveAppealRequest,
    lecturer_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return AttendanceService.resolve_appeal(
        db, lecturer_id, appeal_id, payload.status,
        payload.lecturer_response, payload.new_attendance_status
    )

@router.get("/lecturer/courses/{course_class_id}/students/search")
def search_students(
    course_class_id: str,
    keyword: str,
    lecturer_id: str = Depends(get_current_user_id)
):
    return AttendanceService.search_students_in_course(lecturer_id, course_class_id, keyword)

@router.get("/lecturer/courses/{course_class_id}/statistics")
def get_course_stats(
    course_class_id: str,
    lecturer_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return AttendanceService.get_course_statistics(db, lecturer_id, course_class_id)

@router.get("/lecturer/reports/export")
def export_attendance_report(
    scope: str,  # SESSION | COURSE | STUDENT
    course_class_id: str,
    session_id: Optional[str] = None,
    student_id: Optional[str] = None,
    lecturer_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    csv_content = AttendanceService.export_report_csv(
        db, lecturer_id, scope, course_class_id, session_id, student_id
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_report_{scope.lower()}.csv"}
    )

# ==================== INTERNAL ENDPOINT (CHO NHÓM TRƯỞNG) ====================

@router.get("/internal/students/{student_id}/summary")
def get_student_summary_for_team_lead(
    student_id: str,
    course_class_id: str,
    db: Session = Depends(get_db)
):
    return AttendanceService.get_student_personal_summary(db, student_id, course_class_id)