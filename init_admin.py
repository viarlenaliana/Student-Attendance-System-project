"""Công cụ dòng lệnh khởi tạo tài khoản Admin đầu tiên mà không lưu mật khẩu trong mã nguồn."""
import getpass
import os

from app import create_app
from app.models.user import auth_error, create_user, get_user_by_username


def main():
    app = create_app()
    with app.app_context():
        username = (os.environ.get("INIT_ADMIN_USERNAME") or input("Tên đăng nhập Admin: ")).strip()
        if get_user_by_username(username) is not None:
            print(f"Tài khoản '{username}' đã tồn tại.")
            return

        full_name = (os.environ.get("INIT_ADMIN_FULL_NAME") or input("Họ và tên Admin: ")).strip()
        email = (os.environ.get("INIT_ADMIN_EMAIL") or input("Email Admin: ")).strip()
        password = os.environ.get("INIT_ADMIN_PASSWORD") or getpass.getpass(
            "Mật khẩu Admin (>=8 ký tự, chữ hoa, thường, số - ký tự sẽ ẩn hoàn toàn khi gõ, nhập xong nhấn Enter): "
        )

        try:
            created = create_user(
                {
                    "username": username,
                    "full_name": full_name,
                    "email": email,
                    "role": "admin",
                    "password": password,
                    "must_change_password": False,
                }
            )
            print(f"Đã tạo tài khoản Admin thành công: {created['username']} (user_id={created['user_id']}).")
        except auth_error as error:
            print(f"Lỗi: {error}")


if __name__ == "__main__":
    main()
