from datetime import datetime
from typing import List, Dict, Optional

class SungSessionClient:
    """Phối hợp Sưng: Lấy thông tin buổi học, phương thức điểm danh, QR & Password."""
    @staticmethod
    def get_session_info(session_id: str) -> Optional[Dict]:
        # Thực tế sẽ gọi HTTP REST/gRPC tới service của Sưng
        # Mock cấu trúc dữ liệu chuẩn từ Sưng:
        return {
            "session_id": session_id,
            "course_class_id": "CS101_01",
            "is_open": True,
            "method": "QR_PASSWORD",  # QR | PASSWORD | QR_PASSWORD | MANUAL
            "qr_token": "SECRET_QR_2026",
            "qr_expires_at": datetime(2026, 12, 31, 23, 59, 59),
            "password": "123456"
        }

class DucRosterClient:
    """Phối hợp Đức: Lấy danh sách sinh viên lớp học phần và kiểm tra quyền Lecturer."""
    @staticmethod
    def get_students_in_course(course_class_id: str) -> List[Dict]:
        # Trả về danh sách sinh viên thuộc lớp học phần
        return [
            {"student_id": "SV001", "student_code": "20110001", "full_name": "Nguyễn Văn An"},
            {"student_id": "SV002", "student_code": "20110002", "full_name": "Trần Thị Bình"},
        ]

    @staticmethod
    def is_lecturer_assigned(lecturer_id: str, course_class_id: str) -> bool:
        # Xác thực Lecturer có được phân công dạy lớp học phần này hay không
        return True

class HuyEventPublisher:
    """Phối hợp Huy: Phát sự kiện để gửi thông báo và ghi log hệ thống."""
    @staticmethod
    def publish_event(event_type: str, payload: Dict) -> None:
        # Thực tế đẩy vào RabbitMQ/Kafka hoặc gọi Webhook của Huy
        print(f"[EVENT -> HUY] {event_type}: {payload}")