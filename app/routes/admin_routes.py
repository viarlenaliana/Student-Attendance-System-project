from datetime import datetime
import re
import uuid
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import or_, text
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User
from app.models.student import Student
from app.models.lecturer import Lecturer
from app.models.department import Department
from app.models.course import Course
from app.models.course_section import CourseSection
from app.models.enrollment import Enrollment
from app.models.class_schedule import ClassSchedule
from app.models.attendance_record import AttendanceRecord
from app.models.attendance_session import AttendanceSession
from app.routes.auth import role_required
from app.models.lecturer import Lecturer

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/")
@role_required("admin")
def dashboard():
    total_users = User.query.count()
    total_students = Student.query.count()
    total_lecturers = Lecturer.query.count()
    total_courses = Course.query.count()
    total_sections = CourseSection.query.count()
    total_sessions = AttendanceSession.query.count()

    active_users = User.query.filter_by(is_active=True).count()
    locked_users = User.query.filter_by(status="LOCKED").count()

    recent_users = (
        User.query
        .order_by(User.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_students=total_students,
        total_lecturers=total_lecturers,
        total_courses=total_courses,
        total_sections=total_sections,
        total_sessions=total_sessions,
        active_users=active_users,
        locked_users=locked_users,
        recent_users=recent_users
    )

@admin_bp.route("/users")
@role_required("admin")
def users():
    keyword = request.args.get("keyword", "").strip()
    role = request.args.get("role", "").strip().lower()

    query = User.query
    if keyword:
        query = query.filter(
            or_(
                User.username.ilike(f"%{keyword}%"),
                User.full_name.ilike(f"%{keyword}%"),
                User.email.ilike(f"%{keyword}%"),
                User.user_id.cast(db.String).ilike(f"%{keyword}%"),
                User.user_id.in_(db.session.query(Student.student_id).filter(
                    Student.student_code.ilike(f"%{keyword}%")
                )),
                User.user_id.in_(db.session.query(Lecturer.lecturer_id).filter(
                    Lecturer.lecturer_code.ilike(f"%{keyword}%")
                ))
            )
        )

    if role in ("admin", "student", "lecturer"):
        query = query.filter(User.role == role)

    users_list = query.order_by(User.user_id.desc()).all()
    department_list = Department.query.order_by(
        Department.department_name
    ).all()

    account_ids = {}
    for profile in Student.query.all():
        account_ids[profile.student_id] = profile.student_code
    for profile in Lecturer.query.all():
        account_ids[profile.lecturer_id] = profile.lecturer_code
    for account in users_list:
        if account.role == "admin":
            account_ids[account.user_id] = str(account.user_id)

    return render_template(
        "admin/users.html",
        users=users_list,
        departments=department_list,
        keyword=keyword,
        selected_role=role,
        account_ids=account_ids
    )


@admin_bp.route("/users/create", methods=["POST"])
@role_required("admin")
def create_user():
    account_id = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "").strip().lower()
    department_id = request.form.get("department_id", type=int)
    enrollment_year_raw = request.form.get("enrollment_year", "").strip()

    if not all([account_id, full_name, email, password, role]):
        flash("Please fill in all required account fields.", "danger")
        return redirect(url_for("admin.users", role=role or None))

    patterns = {
        "admin": r"^1\d{5}$",
        "student": r"^2\d{5}$",
        "lecturer": r"^3\d{5}$",
    }
    if role not in patterns or not re.fullmatch(patterns[role], account_id):
        flash("Invalid Account ID. Admin: 1xxxxx, Student: 2xxxxx, Lecturer: 3xxxxx.", "danger")
        return redirect(url_for("admin.users", role=role or None))

    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "danger")
        return redirect(url_for("admin.users", role=role))

    if role == "student" and not department_id:
        default_department = Department.query.order_by(Department.department_id).first()
        department_id = default_department.department_id if default_department else None
    if role in ("student", "lecturer"):
        if not department_id or db.session.get(Department, department_id) is None:
            flash("Please select a valid department for this account.", "danger")
            return redirect(url_for("admin.users", role=role))

    enrollment_year = None
    if role == "student" and enrollment_year_raw:
        try:
            enrollment_year = int(enrollment_year_raw)
            if enrollment_year < 1900 or enrollment_year > 2100:
                raise ValueError
        except ValueError:
            flash("Please enter a valid enrollment year.", "danger")
            return redirect(url_for("admin.users", role=role))

    existing_user = User.query.filter(
        or_(User.username == account_id, User.email == email)
    ).first()
    if existing_user:
        flash("Account ID or email already exists.", "danger")
        return redirect(url_for("admin.users", role=role))

    if role == "student" and Student.query.filter_by(student_code=account_id).first():
        flash("Student Code already exists.", "danger")
        return redirect(url_for("admin.users", role=role))
    if role == "lecturer" and Lecturer.query.filter_by(lecturer_code=account_id).first():
        flash("Lecturer Code already exists.", "danger")
        return redirect(url_for("admin.users", role=role))

    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = User(
            username=account_id,
            password_hash=generate_password_hash(password),
            full_name=full_name,
            email=email,
            role=role,
            is_active=True,
            must_change_password=True,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        db.session.add(user)
        db.session.flush()

        if role == "student":
            db.session.add(Student(
                student_id=user.user_id,
                student_code=account_id,
                department_id=department_id,
                enrollment_year=enrollment_year,
            ))
        elif role == "lecturer":
            db.session.add(Lecturer(
                lecturer_id=user.user_id,
                lecturer_code=account_id,
                department_id=department_id,
            ))

        db.session.commit()
        flash(f"{role.title()} account created successfully. Account ID: {account_id}", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to create account: {error}", "danger")

    return redirect(url_for("admin.users", role=role))


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("Account not found.", "danger")
        return redirect(url_for("admin.users"))

    student_profile = db.session.get(Student, user_id)
    lecturer_profile = db.session.get(Lecturer, user_id)
    departments = Department.query.order_by(Department.department_name).all()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()

        if not full_name or not email:
            flash("Full name and email are required.", "danger")
            return redirect(url_for("admin.edit_user", user_id=user_id))

        duplicate_email = User.query.filter(
            User.email == email, User.user_id != user_id
        ).first()
        if duplicate_email:
            flash("This email is already used by another account.", "danger")
            return redirect(url_for("admin.edit_user", user_id=user_id))

        department_id = request.form.get("department_id", type=int)
        new_code = request.form.get("account_code", "").strip()

        if user.role in ("student", "lecturer"):
            if not new_code or not department_id:
                flash("Account code and department are required.", "danger")
                return redirect(url_for("admin.edit_user", user_id=user_id))
            if db.session.get(Department, department_id) is None:
                flash("Selected department does not exist.", "danger")
                return redirect(url_for("admin.edit_user", user_id=user_id))

            if user.role == "student":
                duplicate_code = Student.query.filter(
                    Student.student_code == new_code,
                    Student.student_id != user_id
                ).first()
                if duplicate_code:
                    flash("This student code is already used.", "danger")
                    return redirect(url_for("admin.edit_user", user_id=user_id))
            else:
                duplicate_code = Lecturer.query.filter(
                    Lecturer.lecturer_code == new_code,
                    Lecturer.lecturer_id != user_id
                ).first()
                if duplicate_code:
                    flash("This lecturer code is already used.", "danger")
                    return redirect(url_for("admin.edit_user", user_id=user_id))

        try:
            user.full_name = full_name
            user.email = email
            user.updated_at = datetime.now()

            if student_profile is not None:
                student_profile.student_code = new_code
                student_profile.department_id = department_id
                year_raw = request.form.get("enrollment_year", "").strip()
                if year_raw:
                    year = int(year_raw)
                    if year < 1900 or year > 2100:
                        raise ValueError("Enrollment year must be between 1900 and 2100.")
                    student_profile.enrollment_year = year
                else:
                    student_profile.enrollment_year = None
                user.username = new_code

            elif lecturer_profile is not None:
                lecturer_profile.lecturer_code = new_code
                lecturer_profile.department_id = department_id
                user.username = new_code

            db.session.commit()
            flash("Account information updated successfully.", "success")
            return redirect(url_for("admin.users"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
        except Exception as error:
            db.session.rollback()
            flash(f"Unable to update account: {error}", "danger")

    account_code = ""
    if student_profile is not None:
        account_code = student_profile.student_code
    elif lecturer_profile is not None:
        account_code = lecturer_profile.lecturer_code

    return render_template(
        "admin/edit_user.html",
        account=user,
        student=student_profile,
        lecturer=lecturer_profile,
        departments=departments,
        account_code=account_code
    )


@admin_bp.route("/users/<int:user_id>/status", methods=["POST"])
@role_required("admin")
def update_user_status(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role == "admin":
        flash("This account cannot be modified.", "danger")
        return redirect(url_for("admin.users"))

    is_active = request.form.get("is_active") == "1"
    user.is_active = is_active
    user.status = "ACTIVE" if is_active else "LOCKED"

    try:
        db.session.commit()
        flash(
            "Account unlocked successfully." if is_active else "Account locked successfully.",
            "success"
        )
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to update account: {error}", "danger")

    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@role_required("admin")
def reset_user_password(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role == "admin":
        flash("This account cannot be reset.", "danger")
        return redirect(url_for("admin.users"))

    user.password_hash = generate_password_hash(DEFAULT_ACCOUNT_PASSWORD)
    user.must_change_password = True
    try:
        db.session.commit()
        flash(f"Password reset. Temporary password: {DEFAULT_ACCOUNT_PASSWORD}", "success")
    except Exception:
        db.session.rollback()
        flash("Unable to reset password.", "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role == "admin":
        flash("This account cannot be deleted.", "danger")
        return redirect(url_for("admin.users"))

    checks = {
        "enrollments": "student_id",
        "attendance_records": "student_id",
        "attendance_sessions": "lecturer_id",
        "course_sections": "lecturer_id",
        "attendance_complaints": "student_id",
        "makeup_attendance_permissions": "student_id"
    }

    try:
        existing_tables = {
            row[0] for row in db.session.execute(text("SHOW TABLES")).fetchall()
        }
        for table, column in checks.items():
            if table not in existing_tables:
                continue
            result = db.session.execute(
                text(f"SELECT 1 FROM `{table}` WHERE `{column}` = :uid LIMIT 1"),
                {"uid": user_id}
            ).first()
            if result:
                flash(
                    "This account has related records and cannot be deleted. Please lock it instead.",
                    "warning"
                )
                return redirect(url_for("admin.users"))

        student_profile = db.session.get(Student, user_id)
        if student_profile is not None:
            db.session.delete(student_profile)

        db.session.delete(user)
        db.session.commit()
        flash("Account deleted successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to delete account: {error}", "danger")

    return redirect(url_for("admin.users"))



DEFAULT_ACCOUNT_PASSWORD = "UniAttend@123"


@admin_bp.route("/accounts/create", methods=["GET", "POST"])
@role_required("admin")
def create_account():
    departments = Department.query.order_by(Department.department_name).all()
    created_credentials = None

    if request.method == "POST":
        role = request.form.get("role", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        personal_code = request.form.get("personal_code", "").strip()
        department_value = request.form.get("department_id", "").strip()
        enrollment_year_value = request.form.get("enrollment_year", "").strip()

        if role not in ("student", "lecturer"):
            flash("Please select Student or Lecturer.", "danger")
        elif not all((full_name, email, personal_code)):
            flash("Please fill in all required fields.", "danger")
        elif User.query.filter(or_(User.username == personal_code, db.func.lower(User.email) == email)).first():
            flash("Account ID or email is already in use.", "danger")
        elif Student.query.filter_by(student_code=personal_code).first() or Lecturer.query.filter_by(lecturer_code=personal_code).first():
            flash("This student/lecturer code already exists.", "danger")
        else:
            # Students inherit the only/default department when no department is
            # selected. This keeps department_id valid without forcing a choice.
            department = None
            if role == "student" and not department_value:
                department = Department.query.order_by(Department.department_id).first()
            elif department_value:
                try:
                    department = db.session.get(Department, int(department_value))
                except (TypeError, ValueError):
                    department = None
            if department is None:
                flash("Please select a valid department. Add a department first if none exists.", "danger")
            else:
                enrollment_year = None
                try:
                    if role == "student" and enrollment_year_value:
                        enrollment_year = int(enrollment_year_value)
                        if not 1900 <= enrollment_year <= 2100:
                            raise ValueError
                    user = User(
                        username=personal_code,
                        password_hash=generate_password_hash(DEFAULT_ACCOUNT_PASSWORD),
                        full_name=full_name,
                        email=email,
                        role=role,
                        is_active=True,
                        must_change_password=True,
                        status="ACTIVE",
                    )
                    db.session.add(user)
                    db.session.flush()

                    if role == "student":
                        db.session.add(Student(
                            student_id=user.user_id,
                            student_code=personal_code,
                            department_id=department.department_id,
                            enrollment_year=enrollment_year,
                        ))
                        id_label = "Student ID"
                    else:
                        db.session.add(Lecturer(
                            lecturer_id=user.user_id,
                            lecturer_code=personal_code,
                            department_id=department.department_id,
                        ))
                        id_label = "Lecturer ID"

                    db.session.commit()
                    created_credentials = {
                        "full_name": full_name,
                        "role": role.title(),
                        "id_label": id_label,
                        "login_id": personal_code,
                        "default_password": DEFAULT_ACCOUNT_PASSWORD,
                    }
                    flash("Account created successfully.", "success")
                except ValueError:
                    db.session.rollback()
                    flash("Please enter a valid enrollment year.", "danger")
                except Exception as error:
                    db.session.rollback()
                    current_app.logger.exception("Admin account creation failed")
                    flash(f"Unable to create account: {error}", "danger")

    return render_template(
        "admin/create_account.html",
        departments=departments,
        created_credentials=created_credentials,
    )


@admin_bp.route("/departments")
@role_required("admin")
def departments():
    department_list = Department.query.order_by(
        Department.department_id.desc()
    ).all()
    return render_template(
        "admin/departments.html",
        departments=department_list
    )


@admin_bp.route("/departments/create", methods=["POST"])
@role_required("admin")
def create_department():
    name = request.form.get("department_name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        flash("Department name is required.", "danger")
        return redirect(url_for("admin.departments"))

    existing = Department.query.filter_by(department_name=name).first()
    if existing:
        flash("Department name already exists.", "danger")
        return redirect(url_for("admin.departments"))

    try:
        # Automatically generate a unique department code
        department_code = "DEPT" + secrets.token_hex(6).upper()

        department = Department(
            department_code=department_code,
            department_name=name,
            description=description or None
        )

        db.session.add(department)
        db.session.commit()

        flash(
            f"Department created successfully. Code: {department_code}",
            "success"
        )

    except Exception as error:
        db.session.rollback()
        flash(f"Unable to create department: {error}", "danger")

    return redirect(url_for("admin.departments"))


@admin_bp.route("/departments/<int:department_id>/update", methods=["POST"])
@role_required("admin")
def update_department(department_id):
    department = db.session.get(Department, department_id)
    if department is None:
        flash("Department not found.", "danger")
        return redirect(url_for("admin.departments"))
    name = request.form.get("department_name", "").strip()
    description = request.form.get("description", "").strip()
    if not name:
        flash("Department name is required.", "danger")
        return redirect(url_for("admin.departments"))
    duplicate = Department.query.filter(
        db.func.lower(Department.department_name) == name.lower(),
        Department.department_id != department_id
    ).first()
    if duplicate:
        flash("Department name already exists.", "danger")
        return redirect(url_for("admin.departments"))
    try:
        department.department_name = name
        department.description = description or None
        db.session.commit()
        flash("Department updated successfully.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Update department failed")
        flash(f"Unable to update department: {error}", "danger")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/departments/<int:department_id>/delete", methods=["POST"])
@role_required("admin")
def delete_department(department_id):
    department = db.session.get(Department, department_id)
    if department is None:
        flash("Department not found.", "danger")
        return redirect(url_for("admin.departments"))

    try:
        has_courses = Course.query.filter_by(department_id=department_id).first()
        if has_courses:
            flash(
                "Cannot delete this department because it has courses.",
                "warning"
            )
            return redirect(url_for("admin.departments"))

        db.session.delete(department)
        db.session.commit()
        flash("Department deleted successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to delete department: {error}", "danger")

    return redirect(url_for("admin.departments"))




@admin_bp.route("/courses")
@role_required("admin")
def courses():
    keyword = request.args.get("keyword", "").strip()
    query = Course.query

    if keyword:
        query = query.filter(
            or_(
                Course.course_code.ilike(f"%{keyword}%"),
                Course.course_name.ilike(f"%{keyword}%")
            )
        )

    course_list = query.order_by(Course.course_id.desc()).all()
    department_list = Department.query.order_by(
        Department.department_name
    ).all()

    return render_template(
        "admin/courses.html",
        courses=course_list,
        departments=department_list,
        keyword=keyword
    )


@admin_bp.route("/courses/create", methods=["POST"])
@role_required("admin")
def create_course():
    course_code = request.form.get("course_code", "").strip()
    course_name = request.form.get("course_name", "").strip()
    department_id = request.form.get("department_id", "").strip()
    credits = request.form.get("credits", "").strip()
    description = request.form.get("description", "").strip()

    if not all([course_code, course_name, department_id, credits]):
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("admin.courses"))

    try:
        department_id = int(department_id)
        credits = int(credits)
        if credits <= 0:
            raise ValueError
    except ValueError:
        flash("Invalid department or credit value.", "danger")
        return redirect(url_for("admin.courses"))

    department = db.session.get(Department, department_id)
    if department is None:
        flash("Selected department does not exist.", "danger")
        return redirect(url_for("admin.courses"))

    existing = Course.query.filter_by(course_code=course_code).first()
    if existing:
        flash("Course code already exists.", "danger")
        return redirect(url_for("admin.courses"))

    try:
        course = Course(
            course_code=course_code,
            course_name=course_name,
            department_id=department_id,
            credits=credits,
            description=description or None
        )
        db.session.add(course)
        db.session.commit()
        flash("Course created successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to create course: {error}", "danger")

    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<int:course_id>/update", methods=["POST"])
@role_required("admin")
def update_course(course_id):
    course = db.session.get(Course, course_id)
    if course is None:
        flash("Course not found.", "danger")
        return redirect(url_for("admin.courses"))

    course_code = request.form.get("course_code", "").strip()
    course_name = request.form.get("course_name", "").strip()
    department_id = request.form.get("department_id", "").strip()
    credits = request.form.get("credits", "").strip()
    description = request.form.get("description", "").strip()

    if not all([course_code, course_name, department_id, credits]):
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("admin.courses"))

    try:
        department_id = int(department_id)
        credits = int(credits)
        if credits <= 0:
            raise ValueError
    except ValueError:
        flash("Invalid department or credit value.", "danger")
        return redirect(url_for("admin.courses"))

    department = db.session.get(Department, department_id)
    if department is None:
        flash("Selected department does not exist.", "danger")
        return redirect(url_for("admin.courses"))

    duplicate = Course.query.filter(
        Course.course_code == course_code,
        Course.course_id != course_id
    ).first()
    if duplicate:
        flash("Course code already exists.", "danger")
        return redirect(url_for("admin.courses"))

    try:
        course.course_code = course_code
        course.course_name = course_name
        course.department_id = department_id
        course.credits = credits
        course.description = description or None
        db.session.commit()
        flash("Course updated successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to update course: {error}", "danger")

    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@role_required("admin")
def delete_course(course_id):
    course = db.session.get(Course, course_id)
    if course is None:
        flash("Course not found.", "danger")
        return redirect(url_for("admin.courses"))

    try:
        related_section = db.session.execute(
            text("""
                SELECT 1
                FROM course_sections
                WHERE course_id = :course_id
                LIMIT 1
            """),
            {"course_id": course_id}
        ).first()

        if related_section:
            flash(
                "Cannot delete this course because it has course sections.",
                "warning"
            )
            return redirect(url_for("admin.courses"))

        db.session.delete(course)
        db.session.commit()
        flash("Course deleted successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to delete course: {error}", "danger")

    return redirect(url_for("admin.courses"))


@admin_bp.route("/course-sections")
@role_required("admin")
def course_sections():

    # Get all course sections
    sections = (
        db.session.query(CourseSection, Course, User)
        .join(Course, CourseSection.course_id == Course.course_id)
        .join(User, CourseSection.lecturer_id == User.user_id)
        .filter(User.role == "lecturer")
        .order_by(CourseSection.section_id.desc())
        .all()
    )

    # Get all courses
    courses = Course.query.order_by(Course.course_code).all()

    # Get active lecturers
    lecturers = (
        User.query
        .join(Lecturer, Lecturer.lecturer_id == User.user_id)
        .filter(
            User.role == "lecturer",
            User.is_active.is_(True),
            User.status == "ACTIVE"
        )
        .order_by(User.full_name)
        .all()
    )

    return render_template(
        "admin/course_sections.html",
        sections=sections,
        courses=courses,
        lecturers=lecturers
    )

    
    


@admin_bp.route("/course-sections/create", methods=["POST"])
@role_required("admin")
def create_course_section():
    course_id = request.form.get("course_id", type=int)
    lecturer_id = request.form.get("lecturer_id", type=int)
    section_code = request.form.get("section_code", "").strip()
    semester = request.form.get("semester", "").strip()
    academic_year = request.form.get("academic_year", "").strip()
    max_students = request.form.get("max_students", type=int)
    status = request.form.get("status", "ACTIVE").strip().upper()

    # Validate required fields
    if not all([course_id, lecturer_id, section_code, semester, academic_year]):
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("admin.course_sections"))

    # Validate maximum students
    if max_students is not None and max_students < 1:
        flash("Maximum students must be greater than 0.", "danger")
        return redirect(url_for("admin.course_sections"))

    # Validate status
    if status not in ["ACTIVE", "INACTIVE"]:
        flash("Invalid course section status.", "danger")
        return redirect(url_for("admin.course_sections"))

    # Check course
    course = Course.query.get(course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for("admin.course_sections"))

        # Check lecturer directly from users table
    lecturer = User.query.filter(
        User.user_id == lecturer_id,
        User.role == "lecturer",
        User.is_active == True,
        User.status == "ACTIVE"
    ).first()

    if not lecturer:
        flash("Lecturer not found or inactive.", "danger")
        return redirect(url_for("admin.course_sections"))

    lecturer_profile = db.session.get(Lecturer, lecturer_id)
    if lecturer_profile is None:
        flash("This lecturer account has no lecturer profile. Please recreate or repair the lecturer profile.", "danger")
        return redirect(url_for("admin.course_sections"))

    # Check duplicate section code
    existing_section = CourseSection.query.filter_by(
        section_code=section_code,
        semester=semester,
        academic_year=academic_year
    ).first()

    if existing_section:
        flash("This section code already exists in the selected semester and academic year.", "danger")
        return redirect(url_for("admin.course_sections"))

    # Create course section
    new_section = CourseSection(
        course_id=course_id,
        lecturer_id=lecturer_id,
        section_code=section_code,
        semester=semester,
        academic_year=academic_year,
        max_students=max_students,
        status=status
    )

    try:
        db.session.add(new_section)
        db.session.commit()
        flash("Course section created successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred while creating the course section.", "danger")
        print("Create course section error:", e)

    return redirect(url_for("admin.course_sections"))


@admin_bp.route("/course-sections/<int:section_id>/update", methods=["POST"])
@role_required("admin")
def update_course_section(section_id):
    section = CourseSection.query.get_or_404(section_id)

    course_id = request.form.get("course_id", type=int)
    lecturer_id = request.form.get("lecturer_id", type=int)
    section_code = request.form.get("section_code", "").strip()
    semester = request.form.get("semester", "").strip()
    academic_year = request.form.get("academic_year", "").strip()
    max_students = request.form.get("max_students", type=int)
    status = request.form.get("status", "ACTIVE").strip().upper()

    # Validate required fields
    if not all([course_id, lecturer_id, section_code, semester, academic_year]):
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("admin.course_sections"))

    if max_students is not None and max_students < 1:
        flash("Maximum students must be greater than 0.", "danger")
        return redirect(url_for("admin.course_sections"))

    if status not in ["ACTIVE", "INACTIVE"]:
        flash("Invalid course section status.", "danger")
        return redirect(url_for("admin.course_sections"))

    course = Course.query.get(course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for("admin.course_sections"))

       # Check lecturer directly from users table
    lecturer = User.query.filter(
        User.user_id == lecturer_id,
        User.role == "lecturer",
        User.is_active == True,
        User.status == "ACTIVE"
    ).first()

    if not lecturer:
        flash("Lecturer not found or inactive.", "danger")
        return redirect(url_for("admin.course_sections"))

    lecturer_profile = db.session.get(Lecturer, lecturer_id)
    if lecturer_profile is None:
        flash("This lecturer account has no lecturer profile. Please repair the lecturer profile first.", "danger")
        return redirect(url_for("admin.course_sections"))

    # Check duplicate section code, excluding current section
    duplicate = CourseSection.query.filter(
        CourseSection.section_code == section_code,
        CourseSection.semester == semester,
        CourseSection.academic_year == academic_year,
        CourseSection.section_id != section_id
    ).first()

    if duplicate:
        flash("This section code already exists.", "danger")
        return redirect(url_for("admin.course_sections"))

    try:
        section.course_id = course_id
        section.lecturer_id = lecturer_id
        section.section_code = section_code
        section.semester = semester
        section.academic_year = academic_year
        section.max_students = max_students
        section.status = status

        db.session.commit()
        flash("Course section updated successfully.", "success")

    except Exception as e:
        db.session.rollback()
        flash("An error occurred while updating the course section.", "danger")
        print("Update course section error:", e)

    return redirect(url_for("admin.course_sections"))


@admin_bp.route("/course-sections/<int:section_id>/delete", methods=["POST"])
@role_required("admin")
def delete_course_section(section_id):
    section = CourseSection.query.get_or_404(section_id)

    try:
        db.session.delete(section)
        db.session.commit()
        flash("Course section deleted successfully.", "success")

    except Exception as e:
        db.session.rollback()
        flash(
            "Cannot delete this course section because it may have related schedules or enrollments.",
            "danger"
        )
        print("Delete course section error:", e)

    return redirect(url_for("admin.course_sections"))

# ==========================================
# CLASS SCHEDULE MANAGEMENT
# ==========================================

@admin_bp.route("/class-schedules")
@role_required("admin")
def class_schedules():
    # Templates use a five-item tuple: schedule, section, course, lecturer, user.
    schedules = (
        db.session.query(ClassSchedule, CourseSection, Course, Lecturer, User)
        .join(CourseSection, ClassSchedule.section_id == CourseSection.section_id)
        .join(Course, CourseSection.course_id == Course.course_id)
        .join(Lecturer, CourseSection.lecturer_id == Lecturer.lecturer_id)
        .join(User, Lecturer.lecturer_id == User.user_id)
        .order_by(ClassSchedule.day_of_week, ClassSchedule.start_time)
        .all()
    )
    # The create/edit forms also expect each section with its related course,
    # lecturer profile and lecturer user record.
    sections = (
        db.session.query(CourseSection, Course, Lecturer, User)
        .join(Course, CourseSection.course_id == Course.course_id)
        .join(Lecturer, CourseSection.lecturer_id == Lecturer.lecturer_id)
        .join(User, Lecturer.lecturer_id == User.user_id)
        .filter(CourseSection.status == "ACTIVE", User.role == "lecturer")
        .order_by(CourseSection.section_code)
        .all()
    )
    day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
    return render_template("admin/class_schedules.html", schedules=schedules, sections=sections, day_names=day_names)


@admin_bp.route("/class-schedules/create", methods=["POST"])
@role_required("admin")
def create_class_schedule():
    try:
        section_id = request.form.get("section_id", type=int)
        day_of_week = request.form.get("day_of_week", type=int)
        start_time_raw = request.form.get("start_time", "").strip()
        end_time_raw = request.form.get("end_time", "").strip()
        room = request.form.get("room", "").strip()
        start_date_raw = (request.form.get("effective_from") or request.form.get("start_date") or "").strip()
        end_date_raw = (request.form.get("effective_to") or request.form.get("end_date") or "").strip()
        if not all([section_id, day_of_week, start_time_raw, end_time_raw, start_date_raw, end_date_raw]):
            raise ValueError("Please fill in all required fields.")
        if day_of_week not in range(1, 8):
            raise ValueError("Invalid day of week.")
        section = db.session.get(CourseSection, section_id)
        if section is None or section.status != "ACTIVE":
            raise ValueError("Course section not found or inactive.")
        start_time = datetime.strptime(start_time_raw, "%H:%M").time()
        end_time = datetime.strptime(end_time_raw, "%H:%M").time()
        effective_from = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
        effective_to = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
        if start_time >= end_time:
            raise ValueError("End time must be after start time.")
        if effective_from > effective_to:
            raise ValueError("Effective To must not be before Effective From.")
        db.session.add(ClassSchedule(section_id=section_id, day_of_week=day_of_week,
            start_time=start_time, end_time=end_time, room=room or None,
            effective_from=effective_from, effective_to=effective_to))
        db.session.commit()
        flash("Class schedule created successfully.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Create class schedule failed")
        flash(f"Unable to create schedule: {error}", "danger")
    return redirect(url_for("admin.class_schedules"))


@admin_bp.route("/class-schedules/<int:schedule_id>/update", methods=["POST"])
@role_required("admin")
def update_class_schedule(schedule_id):
    schedule = db.session.get(ClassSchedule, schedule_id)
    if schedule is None:
        flash("Schedule not found.", "danger")
        return redirect(url_for("admin.class_schedules"))
    try:
        section_id = request.form.get("section_id", type=int)
        day_of_week = request.form.get("day_of_week", type=int)
        start_time_raw = request.form.get("start_time", "").strip()
        end_time_raw = request.form.get("end_time", "").strip()
        room = request.form.get("room", "").strip()
        start_date_raw = (request.form.get("effective_from") or request.form.get("start_date") or "").strip()
        end_date_raw = (request.form.get("effective_to") or request.form.get("end_date") or "").strip()
        if not all([section_id, day_of_week, start_time_raw, end_time_raw, start_date_raw, end_date_raw]):
            raise ValueError("Please fill in all required fields.")
        if day_of_week not in range(1, 8):
            raise ValueError("Invalid day of week.")
        section = db.session.get(CourseSection, section_id)
        if section is None or section.status != "ACTIVE":
            raise ValueError("Course section not found or inactive.")
        start_time = datetime.strptime(start_time_raw, "%H:%M").time()
        end_time = datetime.strptime(end_time_raw, "%H:%M").time()
        effective_from = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
        effective_to = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
        if start_time >= end_time:
            raise ValueError("End time must be after start time.")
        if effective_from > effective_to:
            raise ValueError("Effective To must not be before Effective From.")
        schedule.section_id = section_id
        schedule.day_of_week = day_of_week
        schedule.start_time = start_time
        schedule.end_time = end_time
        schedule.room = room or None
        schedule.effective_from = effective_from
        schedule.effective_to = effective_to
        db.session.commit()
        flash("Class schedule updated successfully.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Update class schedule failed")
        flash(f"Unable to update schedule: {error}", "danger")
    return redirect(url_for("admin.class_schedules"))


@admin_bp.route("/class-schedules/<int:schedule_id>/delete", methods=["POST"])
@role_required("admin")
def delete_class_schedule(schedule_id):
    schedule = db.session.get(ClassSchedule, schedule_id)
    if schedule is None:
        flash("Schedule not found.", "danger")
        return redirect(url_for("admin.class_schedules"))
    try:
        db.session.delete(schedule)
        db.session.commit()
        flash("Class schedule deleted successfully.", "success")
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("Delete class schedule failed")
        flash(f"Unable to delete schedule: {error}", "danger")
    return redirect(url_for("admin.class_schedules"))


# ==========================================
# ENROLLMENT MANAGEMENT
# ==========================================

@admin_bp.route("/enrollments")
@role_required("admin")
def enrollments():
    keyword = request.args.get("keyword", "").strip()
    section_id = request.args.get("section_id", type=int)
    selected_status = request.args.get("status", "").strip().upper()

    base_query = db.session.query(Enrollment, Student, User, CourseSection, Course) \
        .join(Student, Enrollment.student_id == Student.student_id) \
        .join(User, Student.student_id == User.user_id) \
        .join(CourseSection, Enrollment.section_id == CourseSection.section_id) \
        .join(Course, CourseSection.course_id == Course.course_id)
    if keyword:
        base_query = base_query.filter(or_(
            User.username.ilike(f"%{keyword}%"),
            User.full_name.ilike(f"%{keyword}%"),
            Student.student_code.ilike(f"%{keyword}%"),
            CourseSection.section_code.ilike(f"%{keyword}%"),
            Course.course_code.ilike(f"%{keyword}%"),
            Course.course_name.ilike(f"%{keyword}%"),
        ))
    if section_id:
        base_query = base_query.filter(Enrollment.section_id == section_id)
    if selected_status in ("ACTIVE", "INACTIVE"):
        base_query = base_query.filter(Enrollment.status == selected_status)

    enrollment_list = base_query.order_by(Enrollment.enrollment_id.desc()).all()
    students = db.session.query(Student, User).join(User, Student.student_id == User.user_id) \
        .filter(User.role == "student", User.is_active.is_(True), User.status == "ACTIVE") \
        .order_by(User.full_name).all()
    sections = CourseSection.query.order_by(CourseSection.section_code).all()
    active_count = Enrollment.query.filter_by(status="ACTIVE").count()
    inactive_count = Enrollment.query.filter_by(status="INACTIVE").count()
    section_counts = dict(
        db.session.query(Enrollment.section_id, db.func.count(Enrollment.enrollment_id))
        .filter(Enrollment.status == "ACTIVE")
        .group_by(Enrollment.section_id).all()
    )
    return render_template(
        "admin/enrollments.html", enrollments=enrollment_list, students=students,
        sections=sections, keyword=keyword, selected_section_id=section_id,
        selected_status=selected_status, active_count=active_count,
        inactive_count=inactive_count, section_counts=section_counts,
    )


@admin_bp.route("/enrollments/create", methods=["POST"])
@role_required("admin")
def create_enrollment():
    student_id = request.form.get("student_id", type=int)
    section_id = request.form.get("section_id", type=int)

    if not student_id or not section_id:
        flash("Please select both a student and a course section.", "danger")
        return redirect(url_for("admin.enrollments"))

    student = db.session.get(Student, student_id)
    user = db.session.get(User, student_id) if student else None
    section = db.session.get(CourseSection, section_id)

    if student is None or user is None or user.role != "student":
        flash("Selected student does not exist.", "danger")
        return redirect(url_for("admin.enrollments"))

    if not user.is_active or user.status != "ACTIVE":
        flash("Selected student account is inactive.", "warning")
        return redirect(url_for("admin.enrollments"))

    if section is None or section.status != "ACTIVE":
        flash("Selected course section does not exist or is inactive.", "danger")
        return redirect(url_for("admin.enrollments"))

    existing = Enrollment.query.filter_by(
        student_id=student_id,
        section_id=section_id
    ).first()

    if existing:
        if existing.status == "ACTIVE":
            flash("This student is already enrolled in this section.", "warning")
        else:
            existing.status = "ACTIVE"
            try:
                db.session.commit()
                flash("Enrollment reactivated successfully.", "success")
            except Exception as error:
                db.session.rollback()
                flash(f"Unable to reactivate enrollment: {error}", "danger")
        return redirect(url_for("admin.enrollments"))

    if section.max_students:
        active_count = Enrollment.query.filter_by(
            section_id=section_id,
            status="ACTIVE"
        ).count()
        if active_count >= section.max_students:
            flash("This course section has reached its maximum capacity.", "warning")
            return redirect(url_for("admin.enrollments"))

    try:
        enrollment = Enrollment(
            student_id=student_id,
            section_id=section_id,
            status="ACTIVE"
        )
        db.session.add(enrollment)
        db.session.commit()
        flash("Student enrolled successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to create enrollment: {error}", "danger")

    return redirect(url_for("admin.enrollments"))


@admin_bp.route("/enrollments/<int:enrollment_id>/status", methods=["POST"])
@role_required("admin")
def update_enrollment_status(enrollment_id):
    enrollment = db.session.get(Enrollment, enrollment_id)

    if enrollment is None:
        flash("Enrollment not found.", "danger")
        return redirect(url_for("admin.enrollments"))

    status = request.form.get("status", "").strip().upper()
    if status not in ("ACTIVE", "INACTIVE"):
        flash("Invalid enrollment status.", "danger")
        return redirect(url_for("admin.enrollments"))

    try:
        enrollment.status = status
        db.session.commit()
        flash("Enrollment status updated successfully.", "success")
    except Exception as error:
        db.session.rollback()
        flash(f"Unable to update enrollment: {error}", "danger")

    return redirect(url_for("admin.enrollments"))


# =========================================================
# ATTENDANCE MONITORING
# =========================================================

@admin_bp.route("/attendance")
@role_required("admin")
def attendance_monitoring():
    """Show attendance records with searchable and combinable filters."""
    keyword = request.args.get("keyword", "").strip()
    status = request.args.get("status", "").strip().upper()
    section_id = request.args.get("section_id", type=int)
    date_filter = request.args.get("date", "").strip()
    method = request.args.get("method", "").strip().upper()

    query = (
        db.session.query(
            AttendanceRecord,
            AttendanceSession,
            Student,
            User,
            CourseSection,
            Course
        )
        .join(AttendanceSession,
              AttendanceRecord.session_id == AttendanceSession.session_id)
        .join(Student,
              AttendanceRecord.student_id == Student.student_id)
        .join(User, Student.student_id == User.user_id)
        .join(CourseSection,
              AttendanceSession.section_id == CourseSection.section_id)
        .join(Course, CourseSection.course_id == Course.course_id)
    )

    if keyword:
        query = query.filter(or_(
            User.full_name.ilike(f"%{keyword}%"),
            Student.student_code.ilike(f"%{keyword}%"),
            Course.course_code.ilike(f"%{keyword}%"),
            Course.course_name.ilike(f"%{keyword}%"),
            CourseSection.section_code.ilike(f"%{keyword}%")
        ))

    if status in ("PRESENT", "ABSENT", "LATE", "EXCUSED"):
        query = query.filter(AttendanceRecord.attendance_status == status)
    else:
        status = ""

    if section_id:
        query = query.filter(AttendanceSession.section_id == section_id)

    if method in ("QR_CODE", "PASSWORD", "QR_PASSWORD", "MANUAL"):
        query = query.filter(AttendanceSession.attendance_method == method)
    else:
        method = ""

    if date_filter:
        try:
            selected_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            query = query.filter(AttendanceSession.session_date == selected_date)
        except ValueError:
            flash("Invalid date. Please choose a valid date.", "warning")
            date_filter = ""

    records = query.order_by(
        AttendanceSession.session_date.desc(),
        AttendanceSession.start_time.desc(),
        AttendanceRecord.check_in_time.desc()
    ).all()

    # Summary cards reflect the currently filtered result set.
    summary = {
        "total": len(records),
        "present": sum(r.attendance_status == "PRESENT" for r, *_ in records),
        "late": sum(r.attendance_status == "LATE" for r, *_ in records),
        "absent": sum(r.attendance_status == "ABSENT" for r, *_ in records),
        "excused": sum(r.attendance_status == "EXCUSED" for r, *_ in records),
    }

    sections = (
        db.session.query(CourseSection, Course)
        .join(Course, CourseSection.course_id == Course.course_id)
        .order_by(Course.course_code, CourseSection.section_code)
        .all()
    )

    return render_template(
        "admin/attendance_monitoring.html",
        records=records,
        sections=sections,
        keyword=keyword,
        selected_status=status,
        selected_section=section_id,
        selected_date=date_filter,
        selected_method=method,
        summary=summary
    )


# =========================================================
# ATTENDANCE STATISTICS
# =========================================================

@admin_bp.route("/attendance-statistics")
@role_required("admin")
def attendance_statistics():
    """Show attendance statistics with optional date, section and method filters."""
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    section_id = request.args.get("section_id", "").strip()
    method = request.args.get("method", "").strip().upper()

    query = (
        db.session.query(AttendanceRecord, AttendanceSession, CourseSection, Course)
        .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.session_id)
        .join(CourseSection, AttendanceSession.section_id == CourseSection.section_id)
        .join(Course, CourseSection.course_id == Course.course_id)
    )

    if section_id:
        try:
            query = query.filter(AttendanceSession.section_id == int(section_id))
        except ValueError:
            section_id = ""

    if method in ("QR_CODE", "PASSWORD", "QR_PASSWORD", "MANUAL"):
        query = query.filter(AttendanceSession.attendance_method == method)
    else:
        method = ""

    if date_from:
        try:
            date_from_value = datetime.strptime(date_from, "%Y-%m-%d").date()
            query = query.filter(AttendanceSession.session_date >= date_from_value)
        except ValueError:
            flash("Invalid start date. Please choose a valid date.", "warning")
            date_from = ""

    if date_to:
        try:
            date_to_value = datetime.strptime(date_to, "%Y-%m-%d").date()
            query = query.filter(AttendanceSession.session_date <= date_to_value)
        except ValueError:
            flash("Invalid end date. Please choose a valid date.", "warning")
            date_to = ""

    rows = query.order_by(AttendanceSession.session_date.desc()).all()
    statuses = [row[0].attendance_status for row in rows]
    total = len(rows)
    present = statuses.count("PRESENT")
    late = statuses.count("LATE")
    absent = statuses.count("ABSENT")
    excused = statuses.count("EXCUSED")
    attendance_rate = round((present + late) * 100 / total, 1) if total else 0

    # Group results by course and section for the detailed breakdown.
    grouped = {}
    for record, session, section, course in rows:
        key = (course.course_code, course.course_name, section.section_code)
        if key not in grouped:
            grouped[key] = {"course_code": course.course_code,
                            "course_name": course.course_name,
                            "section_code": section.section_code,
                            "total": 0, "present": 0, "late": 0,
                            "absent": 0, "excused": 0}
        item = grouped[key]
        item["total"] += 1
        status_key = record.attendance_status.lower()
        if status_key in ("present", "late", "absent", "excused"):
            item[status_key] += 1

    course_statistics = sorted(
        grouped.values(), key=lambda item: (item["course_code"], item["section_code"])
    )
    sections = (
        db.session.query(CourseSection, Course)
        .join(Course, CourseSection.course_id == Course.course_id)
        .order_by(Course.course_code, CourseSection.section_code)
        .all()
    )

    return render_template(
        "admin/attendance_statistics.html",
        total=total, present=present, absent=absent, late=late,
        excused=excused, attendance_rate=attendance_rate,
        course_statistics=course_statistics, sections=sections,
        selected_section=section_id, selected_method=method,
        date_from=date_from, date_to=date_to
    )