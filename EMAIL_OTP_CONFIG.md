# Hướng dẫn cấu hình Email / OTP và Tích hợp Luồng Tài khoản

> **Lưu ý bảo mật:** Không bao giờ ghi mật khẩu SMTP thật, App Password thật hoặc `SECRET_KEY` thật vào mã nguồn, tài liệu hay Git. Mọi giá trị nhạy cảm phải đặt trong tệp `.env` cục bộ (đã được liệt kê trong `.gitignore`).

---

## 1. Khởi tạo môi trường và tệp `.env`

1. Sao chép tệp mẫu [.env.example](.env.example) thành `.env` tại thư mục gốc dự án:
   ```bash
   copy .env.example .env
   ```
2. Điền giá trị phù hợp cho máy phát triển của bạn:
   - `SECRET_KEY`: chuỗi ngẫu nhiên bảo mật session Flask.
   - `DATABASE_TYPE`: `mysql` (mặc định theo quy ước nhóm) hoặc `sqlite` (dự phòng khi chạy demo/kiểm thử không cần MySQL server).

---

## 2. Cấu hình SMTP gửi Email thông báo & OTP

Các biến môi trường trong `config.py` / `.env`:

| Biến môi trường | Ý nghĩa | Giá trị mẫu (placeholder) |
|---|---|---|
| `MAIL_ENABLED` | Bật/tắt gửi email qua SMTP | `true` (hoặc `false` khi chỉ chạy nội bộ) |
| `MAIL_SERVER` | Địa chỉ máy chủ SMTP | `smtp.gmail.com` hoặc `sandbox.smtp.mailtrap.io` |
| `MAIL_PORT` | Cổng SMTP (`587` TLS hoặc `465` SSL) | `587` |
| `MAIL_USE_TLS` | Bật STARTTLS (thường dùng với cổng `587`) | `true` |
| `MAIL_USE_SSL` | Bật SSL trực tiếp (thường dùng với cổng `465`) | `false` |
| `MAIL_USERNAME` | Tên đăng nhập / email gửi | `your-sender-email@example.com` |
| `MAIL_PASSWORD` | Mật khẩu ứng dụng (App Password) của tài khoản SMTP | `your-smtp-app-password-placeholder` |
| `MAIL_DEFAULT_SENDER` | Tên và email hiển thị người gửi | `Student Attendance System <your-sender-email@example.com>` |
| `MAIL_TIMEOUT_SECONDS` | Thời gian chờ kết nối SMTP (giây) | `10` |

### Gợi ý môi trường thử nghiệm an toàn
- **Mailtrap / Mailpit (khuyên dùng khi dev):** dùng thông tin SMTP sandbox của Mailtrap hoặc Mailpit cục bộ để kiểm tra email OTP và email thông báo mà không gửi ra email thật.
- **Gmail SMTP:** bật xác thực 2 bước trên tài khoản Google, tạo **App Password** 16 ký tự và điền vào `MAIL_PASSWORD` trong `.env` (tuyệt đối không dùng mật khẩu đăng nhập chính và không commit lên Git).

---

## 3. Cấu hình chính sách OTP và Mật khẩu

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `PASSWORD_MIN_LENGTH` | `8` | Độ dài tối thiểu của mật khẩu (yêu cầu có chữ hoa, chữ thường, chữ số) |
| `OTP_EXPIRY_MINUTES` | `10` | Thời gian hiệu lực của mã OTP (phút) |
| `OTP_MAX_ATTEMPTS` | `5` | Số lần nhập sai OTP tối đa trước khi mã OTP bị vô hiệu hóa |
| `OTP_RESEND_COOLDOWN_SECONDS` | `60` | Thời gian chờ tối thiểu giữa hai lần yêu cầu gửi lại OTP (giây) |

### Quy tắc bảo mật OTP & Mật khẩu
- Mật khẩu và mã OTP được băm bằng `werkzeug.security.generate_password_hash` trước khi lưu xuống database (`users.password_hash`, `password_otps.otp_hash`).
- Không trả mật khẩu hoặc OTP thật về HTML, JavaScript, cookie session hay ghi vào log ứng dụng.
- Người dùng chỉ được đặt lại mật khẩu sau khi OTP đã được xác minh thành công (`verify_password_otp`).
- Tài khoản mới do Admin tạo bắt buộc phải đổi mật khẩu trong lần đăng nhập đầu tiên (`must_change_password = 1`).

---

## 4. Tạo tài khoản Admin đầu tiên

Hệ thống **không** có chức năng tự đăng ký. Để tạo Admin đầu tiên:

- **Cách 1 (khuyên dùng):** Chạy công cụ tương tác dòng lệnh:
  ```bash
  venv\Scripts\python.exe init_admin.py
  ```
- **Cách 2:** Khai báo tạm các biến `INIT_ADMIN_USERNAME`, `INIT_ADMIN_EMAIL`, `INIT_ADMIN_FULL_NAME`, `INIT_ADMIN_PASSWORD` trong `.env` khi khởi động lần đầu, sau đó xóa `INIT_ADMIN_PASSWORD` khỏi `.env`.

---

## 5. Giao diện hàm dùng chung cho các module trong nhóm

### `app/models/user.py`
- `get_current_user()` -> trả về dict thông tin tài khoản hiện tại (đã loại bỏ `password_hash`) hoặc `None`.
- `check_user_permission(user_id, role, resource_id=None)` -> trả về `True`/`False`.

### `app/models/activity_log.py`
- `create_activity_log(user_id, action, object_type, object_id=None, result="success", details=None)` -> ghi nhận sự kiện vào bảng `activity_logs`. Người dùng thường không có quyền xem, sửa hoặc xóa log.

### `app/models/notification.py`
- `create_notification(user_id, title, message, notification_type="system", related_id=None, send_email=True)`
- Hàm phối hợp theo 4 nhóm sự kiện được đặc tả:
  - `notify_schedule_event(user_ids, schedule_data, event_action="updated")` (`notification_type="schedule"`)
  - `notify_attendance_session_event(user_ids, session_data, event_action="opened")` (`notification_type="attendance_session"`)
  - `notify_attendance_result_event(user_id, attendance_data)` (`notification_type="attendance_result"`)
  - `notify_complaint_response_event(user_id, complaint_data)` (`notification_type="complaint_response"`)
