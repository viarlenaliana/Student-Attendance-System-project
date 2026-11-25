from getpass import getpass

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.admin import Admin


app = create_app()


def create_admin():
    print("\n===== UNIATTEND - CREATE ADMIN =====\n")

    username = input("Admin username: ").strip()
    full_name = input("Full name: ").strip()
    email = input("Admin email: ").strip()

    password = getpass("Admin password: ")
    confirm_password = getpass("Confirm password: ")

    if not all([username, full_name, email, password]):
        print("ERROR: All fields are required.")
        return

    if password != confirm_password:
        print("ERROR: Passwords do not match.")
        return

    if len(password) < 8:
        print("ERROR: Password must contain at least 8 characters.")
        return

    with app.app_context():

        existing = User.query.filter(
            (User.username == username) |
            (User.email == email)
        ).first()

        if existing:
            print("ERROR: Username or email already exists.")
            return

        try:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                full_name=full_name,
                email=email,
                role="admin",
                is_active=True,
                must_change_password=False,
                status="ACTIVE"
            )

            db.session.add(user)
            db.session.flush()

            admin = Admin(user_id=user.user_id)

            db.session.add(admin)
            db.session.commit()

            print("\nSUCCESS! Admin account created.")
            print("Username:", username)
            print("Role: admin")

        except Exception as error:
            db.session.rollback()
            print("ERROR:", error)


if __name__ == "__main__":
    create_admin()