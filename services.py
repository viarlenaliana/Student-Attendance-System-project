import io
import csv
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import (
    AttendanceRecord, AttendanceAuditLog, AttendanceAttempt, AttendanceAppeal,
    AttendanceStatus, AttendanceMethod, AppealStatus
)
from integrations import SungSessionClient, DucRosterClient, HuyEventPublisher

MAX_PASSWORD_ATTEMPTS = 5

class AttendanceService:

    # ---------------------------------------------------------
    # 1. STUDENT CHECK-IN (4 PHƯƠNG THỨC + CHỐNG TRÙNG + KHÓA 5 LẦN)
    # ---------------------------------------------------------
    @staticmethod
    def student_check_in(
        db: Session, student_id: str, session_id: str,
        qr_token: Optional[str], password: Optional[str]
    ) -> AttendanceRecord:
        # 1. Lấy thông tin buổi học từ Sưng
        session_info = SungSessionClient.get_session_info(session_id)
        if not session_info or not session_info.get("is_open"):
            raise HTTPException(status_code=400, detail="Buổi học không tồn tại hoặc đã đóng điểm danh.")

        course_class_id = session_info["course_class_id"]
        method = session_info["method"]

        # 2. Kiểm tra sinh viên có thuộc danh sách lớp từ Đức không
        roster = DucRosterClient.get_students_in_course(course_class_id)
        if not any(s["student_id"] == student_id for s in roster):
            raise HTTPException(status_code=403, detail="Sinh viên không thuộc danh sách lớp học phần này.")

        # 3. Kiểm tra trùng lặp sớm (Idempotency)
        existing_record = db.query(AttendanceRecord).filter_by(
            session_id=session_id, student_id=student_id
        ).first()
        if existing_record and existing_record.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]:
            return existing_record  # Không tạo bản ghi trùng, trả về kết quả đã ghi nhận

        # 4. Chặn nếu phương thức buổi học là MANUAL
        if method == AttendanceMethod.MANUAL.value:
            raise HTTPException(status_code=403, detail="Buổi học này áp dụng điểm danh thủ công bởi Giảng viên.")

        # 5. Xử lý xác thực theo từng phương thức
        now = datetime.utcnow()

        if method == AttendanceMethod.QR.value:
            AttendanceService._validate_qr(session_info, qr_token, now)

        elif method == AttendanceMethod.PASSWORD.value:
            AttendanceService._validate_password_with_lock(db, session_id, student_id, session_info, password, now)

        elif method == AttendanceMethod.QR_PASSWORD.value:
            # Kiểm tra khóa trước, sau đó kiểm tra cả QR và Password
            AttendanceService._check_attempt_locked(db, session_id, student_id)
            AttendanceService._validate_qr(session_info, qr_token, now)
            AttendanceService._validate_password_with_lock(db, session_id, student_id, session_info, password, now)

        # 6. Ghi nhận nguyên tử (Atomic Upsert) chống Race Condition khi bấm nhiều lần
        try:
            if existing_record:
                existing_record.status = AttendanceStatus.PRESENT
                existing_record.method_used = AttendanceMethod(method)
                existing_record.check_in_at = now
                record = existing_record
            else:
                record = AttendanceRecord(
                    session_id=session_id,
                    course_class_id=course_class_id,
                    student_id=student_id,
                    status=AttendanceStatus.PRESENT,
                    method_used=AttendanceMethod(method),
                    check_in_at=now
                )
                db.add(record)

            db.commit()
            db.refresh(record)
        except IntegrityError:
            db.rollback()
            # Nếu 2 request đồng thời vượt qua bước 3 cùng lúc, lấy bản ghi vừa được commit
            record = db.query(AttendanceRecord).filter_by(
                session_id=session_id, student_id=student_id
            ).first()
            return record

        # 7. Chỉ báo cho Huy sau khi DB đã lưu thành công
        HuyEventPublisher.publish_event("ATTENDANCE_RECORDED", {
            "record_id": record.id,
            "session_id": session_id,
            "student_id": student_id,
            "status": record.status.value,
            "check_in_at": record.check_in_at.isoformat()
        })

        return record

    @staticmethod
    def _validate_qr(session_info: Dict, qr_token: Optional[str], now: datetime):
        if not qr_token or qr_token != session_info.get("qr_token"):
            raise HTTPException(status_code=400, detail="Mã QR không hợp lệ hoặc không thuộc buổi học này.")
        if now > session_info.get("qr_expires_at"):
            raise HTTPException(status_code=400, detail="Mã QR đã hết hiệu lực.")

    @staticmethod
    def _check_attempt_locked(db: Session, session_id: str, student_id: str) -> AttendanceAttempt:
        attempt = db.query(AttendanceAttempt).filter_by(
            session_id=session_id, student_id=student_id
        ).first()
        if not attempt:
            attempt = AttendanceAttempt(session_id=session_id, student_id=student_id, failed_count=0)
            db.add(attempt)
            db.flush()
        if attempt.is_locked_for_session:
            raise HTTPException(
                status_code=423,
                detail="Bạn đã nhập sai mật khẩu 5 lần. Chức năng nhập mật khẩu bị khóa trong buổi học này."
            )
        return attempt

    @staticmethod
    def _validate_password_with_lock(
        db: Session, session_id: str, student_id: str,
        session_info: Dict, password: Optional[str], now: datetime
    ):
        attempt = AttendanceService._check_attempt_locked(db, session_id, student_id)

        if not password or password != session_info.get("password"):
            attempt.failed_count += 1
            attempt.last_attempt_at = now
            if attempt.failed_count >= MAX_PASSWORD_ATTEMPTS:
                attempt.is_locked_for_session = True
            db.commit()  # Lưu lại số lần sai ngay lập tức

            remaining = MAX_PASSWORD_ATTEMPTS - attempt.failed_count
            if remaining <= 0:
                raise HTTPException(
                    status_code=423,
                    detail="Bạn đã nhập sai mật khẩu 5 lần. Chức năng nhập mật khẩu bị khóa trong buổi học này."
                )
            raise HTTPException(
                status_code=400,
                detail=f"Mật khẩu điểm danh không chính xác. Bạn còn {remaining} lần thử."
            )

        # Nhập đúng -> reset bộ đếm lỗi
        attempt.failed_count = 0
        attempt.last_attempt_at = now

    # ---------------------------------------------------------
    # 2. LECTURER CHỈNH SỬA KẾT QUẢ + LƯU LỊCH SỬ AUDIT LOG
    # ---------------------------------------------------------
    @staticmethod
    def lecturer_update_status(
        db: Session, lecturer_id: str, record_id: int,
        new_status: AttendanceStatus, reason: Optional[str] = None
    ) -> AttendanceRecord:
        record = db.query(AttendanceRecord).filter_by(id=record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi điểm danh.")

        if not DucRosterClient.is_lecturer_assigned(lecturer_id, record.course_class_id):
            raise HTTPException(status_code=403, detail="Bạn không có quyền chỉnh sửa lớp học phần này.")

        if record.status == new_status:
            return record

        previous_status = record.status
        record.status = new_status

        # Ghi bắt buộc lịch sử chỉnh sửa
        audit_log = AttendanceAuditLog(
            record_id=record.id,
            changed_by=lecturer_id,
            previous_status=previous_status,
            new_status=new_status,
            reason=reason,
            changed_at=datetime.utcnow()
        )
        db.add(audit_log)
        db.commit()
        db.refresh(record)

        # Phát thông báo cho Huy
        HuyEventPublisher.publish_event("ATTENDANCE_UPDATED", {
            "record_id": record.id,
            "student_id": record.student_id,
            "lecturer_id": lecturer_id,
            "previous_status": previous_status.value,
            "new_status": new_status.value
        })

        return record

    # ---------------------------------------------------------
    # 3. MANUAL ROLL-CALL (CHỈ DÙNG KHI PHƯƠNG THỨC BUỔI LÀ MANUAL)
    # ---------------------------------------------------------
    @staticmethod
    def manual_roll_call(
        db: Session, lecturer_id: str, session_id: str, items: List[Dict]
    ) -> List[AttendanceRecord]:
        session_info = SungSessionClient.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="Không tìm thấy buổi học.")

        # Ràng buộc phối hợp Sưng: Chỉ dùng khi method == MANUAL
        if session_info.get("method") != AttendanceMethod.MANUAL.value:
            raise HTTPException(
                status_code=400,
                detail="Chỉ được dùng điểm danh thủ công khi phương thức của buổi học là MANUAL."
            )

        course_class_id = session_info["course_class_id"]
        if not DucRosterClient.is_lecturer_assigned(lecturer_id, course_class_id):
            raise HTTPException(status_code=403, detail="Không có quyền điểm danh lớp học phần này.")

        updated_records = []
        now = datetime.utcnow()

        for item in items:
            s_id = item["student_id"]
            st = item["status"]
            record = db.query(AttendanceRecord).filter_by(session_id=session_id, student_id=s_id).first()

            if record:
                if record.status != st:
                    log = AttendanceAuditLog(
                        record_id=record.id,
                        changed_by=lecturer_id,
                        previous_status=record.status,
                        new_status=st,
                        reason="Manual roll-call update",
                        changed_at=now
                    )
                    db.add(log)
                    record.status = st
                    record.method_used = AttendanceMethod.MANUAL
            else:
                record = AttendanceRecord(
                    session_id=session_id,
                    course_class_id=course_class_id,
                    student_id=s_id,
                    status=st,
                    method_used=AttendanceMethod.MANUAL,
                    check_in_at=now if st in [AttendanceStatus.PRESENT, AttendanceStatus.LATE] else None
                )
                db.add(record)

            updated_records.append(record)

        db.commit()
        return updated_records

    # ---------------------------------------------------------
    # 4. KHIẾU NẠI ĐIỂM DANH (STUDENT GỬI & LECTURER XỬ LÝ)
    # ---------------------------------------------------------
    @staticmethod
    def create_appeal(
        db: Session, student_id: str, record_id: int, reason: str, evidence_url: Optional[str]
    ) -> AttendanceAppeal:
        record = db.query(AttendanceRecord).filter_by(id=record_id, student_id=student_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy kết quả điểm danh của bạn.")

        # Chặn mở trùng khiếu nại đang xử lý
        active_appeal = db.query(AttendanceAppeal).filter(
            AttendanceAppeal.record_id == record_id,
            AttendanceAppeal.status.in_([AppealStatus.PENDING, AppealStatus.IN_PROGRESS])
        ).first()
        if active_appeal:
            raise HTTPException(status_code=400, detail="Bạn đã có khiếu nại đang chờ xử lý cho buổi học này.")

        appeal = AttendanceAppeal(
            record_id=record_id,
            student_id=student_id,
            reason=reason,
            evidence_url=evidence_url,
            status=AppealStatus.PENDING
        )
        db.add(appeal)
        db.commit()
        db.refresh(appeal)

        HuyEventPublisher.publish_event("APPEAL_CREATED", {
            "appeal_id": appeal.id,
            "record_id": record_id,
            "student_id": student_id
        })
        return appeal

    @staticmethod
    def resolve_appeal(
        db: Session, lecturer_id: str, appeal_id: int,
        new_status: AppealStatus, lecturer_response: Optional[str],
        new_attendance_status: Optional[AttendanceStatus] = None
    ) -> AttendanceAppeal:
        appeal = db.query(AttendanceAppeal).filter_by(id=appeal_id).first()
        if not appeal:
            raise HTTPException(status_code=404, detail="Không tìm thấy khiếu nại.")

        record = appeal.record
        if not DucRosterClient.is_lecturer_assigned(lecturer_id, record.course_class_id):
            raise HTTPException(status_code=403, detail="Bạn không phụ trách lớp học phần của khiếu nại này.")

        appeal.lecturer_id = lecturer_id
        appeal.status = new_status
        appeal.lecturer_response = lecturer_response

        if new_status in [AppealStatus.ACCEPTED, AppealStatus.REJECTED]:
            appeal.resolved_at = datetime.utcnow()

        # Nếu ACCEPTED -> tự động cập nhật trạng thái điểm danh & ghi audit log
        if new_status == AppealStatus.ACCEPTED:
            target_att_status = new_attendance_status or AttendanceStatus.PRESENT
            if record.status != target_att_status:
                log = AttendanceAuditLog(
                    record_id=record.id,
                    changed_by=lecturer_id,
                    previous_status=record.status,
                    new_status=target_att_status,
                    reason=f"Chấp nhận khiếu nại #{appeal.id}: {lecturer_response or ''}"
                )
                db.add(log)
                record.status = target_att_status

        db.commit()
        db.refresh(appeal)

        if new_status in [AppealStatus.ACCEPTED, AppealStatus.REJECTED]:
            HuyEventPublisher.publish_event("APPEAL_RESOLVED", {
                "appeal_id": appeal.id,
                "student_id": appeal.student_id,
                "status": new_status.value,
                "lecturer_response": lecturer_response
            })

        return appeal

    # ---------------------------------------------------------
    # 5. TÌM KIẾM SINH VIÊN TRONG LỚP PHÂN CÔNG
    # ---------------------------------------------------------
    @staticmethod
    def search_students_in_course(lecturer_id: str, course_class_id: str, keyword: str) -> List[Dict]:
        if not DucRosterClient.is_lecturer_assigned(lecturer_id, course_class_id):
            raise HTTPException(status_code=403, detail="Không có quyền tìm kiếm ngoài lớp được phân công.")

        roster = DucRosterClient.get_students_in_course(course_class_id)
        kw = keyword.strip().lower()
        # Chỉ lọc trong danh sách lớp đã xác thực quyền
        return [
            s for s in roster
            if kw in s["full_name"].lower() or kw in s["student_code"].lower()
        ]

    # ---------------------------------------------------------
    # 6. THỐNG KÊ & XUẤT BÁO CÁO (SESSION / COURSE / STUDENT)
    # ---------------------------------------------------------
    @staticmethod
    def get_course_statistics(db: Session, lecturer_id: str, course_class_id: str) -> Dict:
        if not DucRosterClient.is_lecturer_assigned(lecturer_id, course_class_id):
            raise HTTPException(status_code=403, detail="Không có quyền xem thống kê lớp này.")

        records = db.query(AttendanceRecord).filter_by(course_class_id=course_class_id).all()
        total = len(records)
        counts = {s.value: 0 for s in AttendanceStatus}
        for r in records:
            counts[r.status.value] += 1

        return {
            "course_class_id": course_class_id,
            "total_records": total,
            "breakdown": counts,
            "attendance_rate": round(((counts["PRESENT"] + counts["LATE"]) / total * 100), 2) if total else 0.0
        }

    @staticmethod
    def export_report_csv(
        db: Session, lecturer_id: str, scope: str,
        course_class_id: str, session_id: Optional[str] = None, student_id: Optional[str] = None
    ) -> str:
        if not DucRosterClient.is_lecturer_assigned(lecturer_id, course_class_id):
            raise HTTPException(status_code=403, detail="Không có quyền xuất báo cáo lớp này.")

        query = db.query(AttendanceRecord).filter_by(course_class_id=course_class_id)

        if scope == "SESSION":
            if not session_id:
                raise HTTPException(status_code=400, detail="Thiếu session_id cho báo cáo theo buổi.")
            query = query.filter_by(session_id=session_id)
        elif scope == "STUDENT":
            if not student_id:
                raise HTTPException(status_code=400, detail="Thiếu student_id cho báo cáo theo sinh viên.")
            query = query.filter_by(student_id=student_id)
        elif scope != "COURSE":
            raise HTTPException(status_code=400, detail="Scope không hợp lệ (chọn SESSION, COURSE hoặc STUDENT).")

        records = query.all()
        roster_map = {s["student_id"]: s for s in DucRosterClient.get_students_in_course(course_class_id)}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Session ID", "Student Code", "Full Name", "Status", "Method", "Check-in Time"])

        for r in records:
            st_info = roster_map.get(r.student_id, {"student_code": r.student_id, "full_name": "N/A"})
            writer.writerow([
                r.session_id,
                st_info["student_code"],
                st_info["full_name"],
                r.status.value,
                r.method_used.value if r.method_used else "",
                r.check_in_at.strftime("%Y-%m-%d %H:%M:%S") if r.check_in_at else ""
            ])

        return output.getvalue()

    # ---------------------------------------------------------
    # 7. API CHO NHÓM TRƯỞNG: LỊCH SỬ & THỐNG KÊ CÁ NHÂN STUDENT
    # ---------------------------------------------------------
    @staticmethod
    def get_student_personal_summary(db: Session, student_id: str, course_class_id: str) -> Dict:
        records = db.query(AttendanceRecord).filter_by(
            student_id=student_id, course_class_id=course_class_id
        ).order_by(AttendanceRecord.id.asc()).all()

        counts = {s.value: 0 for s in AttendanceStatus}
        history = []
        for r in records:
            counts[r.status.value] += 1
            history.append({
                "record_id": r.id,
                "session_id": r.session_id,
                "status": r.status.value,
                "method_used": r.method_used.value if r.method_used else None,
                "check_in_at": r.check_in_at.isoformat() if r.check_in_at else None
            })

        total = len(records)
        return {
            "student_id": student_id,
            "course_class_id": course_class_id,
            "summary": counts,
            "attendance_rate": round(((counts["PRESENT"] + counts["LATE"]) / total * 100), 2) if total else 0.0,
            "history": history
        }