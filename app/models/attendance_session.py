attendance_methods = [
    "QR code",
    "Password",
    "QR code combined with password",
    "Manual attendance"
]

attendance_session_statuses = [
    "Scheduled",
    "Open",
    "Ended"
]


def check_attendance_method(method):
    """
    Kiểm tra phương thức điểm danh có hợp lệ không.
    """
    return method in attendance_methods


def check_attendance_session_status(status):
    """
    Kiểm tra trạng thái buổi điểm danh.
    """
    return status in attendance_session_statuses
