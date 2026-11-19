"""admin: student lecturer, khoa/phòng ban, môn học, lớp học phần, đăng ký học.

route chỉ nhận request, kiểm tra quyền, gọi hàm
nghiệp vụ trong app/models rồi trả template/redirect.
"""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.models.academic import (
    academic_error, add_student_to_class, create_class, create_course, create_department,
    get_class_by_id, get_class_list, get_course_list, get_department_list, get_enrollment_list,
    remove_student_from_class, update_class, update_course, update_department,
)
from app.models.activity_log import create_activity_log
from app.models.lecturer import create_lecturer, get_lecturer_list, update_lecturer
from app.models.student import create_student, get_student_list, update_student
from app.models.user import check_user_permission, get_current_user

academic_bp = Blueprint("academic", __name__, url_prefix="/admin")


@academic_bp.route("/")
@academic_bp.route("")
def admin_home():
    return redirect(url_for("academic.student_list_page"))


def admin_required(view_function):
    """Kiểm tra đăng nhập và quyền Admin ở phía server."""
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return redirect(url_for("auth.login_page"))
        if not check_user_permission(user["user_id"], "admin"):
            abort(403)
        return view_function(*args, **kwargs)
    return wrapper


def run_admin_action(action_function, success_message, redirect_endpoint, log_action, object_type, **redirect_values):
    """Gọi hàm nghiệp vụ, báo thành công chỉ sau khi lưu xong, ghi activity log."""
    user = get_current_user()
    try:
        record = action_function()
    except academic_error as error:
        flash(str(error), "danger")
        create_activity_log(user["user_id"], log_action, object_type, None, "failed")
    else:
        flash(success_message, "success")
        object_id = record.get(object_type + "_id") if isinstance(record, dict) else None
        create_activity_log(user["user_id"], log_action, object_type, object_id, "success")
    return redirect(url_for(redirect_endpoint, **redirect_values))


def department_options():
    return [{"value": item["department_id"], "label": item["department_name"]} for item in get_department_list()]


def render_entity_page(title, columns, fields, rows, id_key, create_endpoint, update_endpoint):
    return render_template(
        "admin/academic/entity_list.html", title=title, columns=columns, fields=fields,
        rows=rows, id_key=id_key, create_endpoint=create_endpoint, update_endpoint=update_endpoint,
    )


# ---------- Student ----------
@academic_bp.route("/students")
@admin_required
def student_list_page():
    fields = [
        {"name": "full_name", "label": "Họ tên", "type": "text", "required": True},
        {"name": "email", "label": "Email", "type": "email", "required": True},
        {"name": "user_id", "label": "Mã tài khoản (user_id)", "type": "number"},
        {"name": "department_id", "label": "Khoa/phòng ban", "type": "select", "options": department_options()},
    ]
    columns = [("student_id", "Mã SV"), ("full_name", "Họ tên"), ("email", "Email"),
               ("department_name", "Khoa/phòng ban")]
    return render_entity_page("Sinh viên", columns, fields, get_student_list(), "student_id",
                              "academic.student_create_action", "academic.student_update_action")


@academic_bp.route("/students/create", methods=["POST"])
@admin_required
def student_create_action():
    form_data = request.form.to_dict()
    return run_admin_action(lambda: create_student(form_data), "Đã thêm sinh viên.",
                            "academic.student_list_page", "create_student", "student")


@academic_bp.route("/students/<int:student_id>/update", methods=["POST"])
@admin_required
def student_update_action(student_id):
    form_data = request.form.to_dict()
    return run_admin_action(lambda: update_student(student_id, form_data), "Đã cập nhật sinh viên.",
                            "academic.student_list_page", "update_student", "student")


# ---------- Lecturer ----------
@academic_bp.route("/lecturers")
@admin_required
def lecturer_list_page():
    fields = [
        {"name": "full_name", "label": "Họ tên", "type": "text", "required": True},
        {"name": "email", "label": "Email", "type": "email", "required": True},
        {"name": "user_id", "label": "Mã tài khoản (user_id)", "type": "number"},
        {"name": "department_id", "label": "Khoa/phòng ban", "type": "select", "options": department_options()},
    ]
    columns = [("lecturer_id", "Mã GV"), ("full_name", "Họ tên"), ("email", "Email"),
               ("department_name", "Khoa/phòng ban")]
    return render_entity_page("Giảng viên", columns, fields, get_lecturer_list(), "lecturer_id",
                              "academic.lecturer_create_action", "academic.lecturer_update_action")


@academic_bp.route("/lecturers/create", methods=["POST"])
@admin_required
def lecturer_create_action():
    form_data = request.form.to_dict()
    return run_admin_action(lambda: create_lecturer(form_data), "Đã thêm giảng viên.",
                            "academic.lecturer_list_page", "create_lecturer", "lecturer")


@academic_bp.route("/lecturers/<int:lecturer_id>/update", methods=["POST"])
@admin_required
def lecturer_update_action(lecturer_id):
    form_data = request.form.to_dict()
    return run_admin_action(lambda: update_lecturer(lecturer_id, form_data), "Đã cập nhật giảng viên.",
                            "academic.lecturer_list_page", "update_lecturer", "lecturer")


# ---------- Khoa/phòng ban ----------
@academic_bp.route("/departments")
@admin_required
def department_list_page():
    fields = [{"name": "department_name", "label": "Tên khoa/phòng ban", "type": "text", "required": True}]
    columns = [("department_id", "Mã"), ("department_name", "Tên khoa/phòng ban")]
    return render_entity_page("Khoa/phòng ban", columns, fields, get_department_list(), "department_id",
                              "academic.department_create_action", "academic.department_update_action")


@academic_bp.route("/departments/create", methods=["POST"])
@admin_required
def department_create_action():
    form_data = request.form.to_dict()
    return run_admin_action(lambda: create_department(form_data), "Đã thêm khoa/phòng ban.",
                            "academic.department_list_page", "create_department", "department")


@academic_bp.route("/departments/<int:department_id>/update", methods=["POST"])
@admin_required
def department_update_action(department_id):
    form_data = request.form.to_dict()
    return run_admin_action(lambda: update_department(department_id, form_data), "Đã cập nhật khoa/phòng ban.",
                            "academic.department_list_page", "update_department", "department")


# ---------- Môn học ----------
@academic_bp.route("/courses")
@admin_required
def course_list_page():
    fields = [
        {"name": "course_name", "label": "Tên môn học", "type": "text", "required": True},
        {"name": "department_id", "label": "Khoa/phòng ban", "type": "select", "options": department_options()},
    ]
    columns = [("course_id", "Mã"), ("course_name", "Tên môn học"), ("department_name", "Khoa/phòng ban")]
    return render_entity_page("Môn học", columns, fields, get_course_list(), "course_id",
                              "academic.course_create_action", "academic.course_update_action")


@academic_bp.route("/courses/create", methods=["POST"])
@admin_required
def course_create_action():
    form_data = request.form.to_dict()
    return run_admin_action(lambda: create_course(form_data), "Đã thêm môn học.",
                            "academic.course_list_page", "create_course", "course")


@academic_bp.route("/courses/<int:course_id>/update", methods=["POST"])
@admin_required
def course_update_action(course_id):
    form_data = request.form.to_dict()
    return run_admin_action(lambda: update_course(course_id, form_data), "Đã cập nhật môn học.",
                            "academic.course_list_page", "update_course", "course")


# ---------- Lớp học phần ----------
@academic_bp.route("/classes")
@admin_required
def class_list_page():
    fields = [
        {"name": "class_name", "label": "Tên lớp học phần", "type": "text", "required": True},
        {"name": "course_id", "label": "Môn học", "type": "select", "required": True,
         "options": [{"value": item["course_id"], "label": item["course_name"]} for item in get_course_list()]},
        {"name": "lecturer_id", "label": "Giảng viên phụ trách", "type": "select",
         "options": [{"value": item["lecturer_id"], "label": item["full_name"]} for item in get_lecturer_list()]},
        {"name": "semester", "label": "Học kỳ", "type": "text"},
    ]
    columns = [("class_id", "Mã"), ("class_name", "Lớp học phần"), ("course_name", "Môn học"),
               ("lecturer_name", "Giảng viên"), ("semester", "Học kỳ"), ("student_count", "Sĩ số")]
    return render_template(
        "admin/academic/entity_list.html", title="Lớp học phần", columns=columns, fields=fields,
        rows=get_class_list(), id_key="class_id", create_endpoint="academic.class_create_action",
        update_endpoint="academic.class_update_action", enrollment_endpoint="academic.enrollment_list_page",
    )


@academic_bp.route("/classes/create", methods=["POST"])
@admin_required
def class_create_action():
    form_data = request.form.to_dict()
    return run_admin_action(lambda: create_class(form_data), "Đã thêm lớp học phần.",
                            "academic.class_list_page", "create_class", "class")


@academic_bp.route("/classes/<int:class_id>/update", methods=["POST"])
@admin_required
def class_update_action(class_id):
    form_data = request.form.to_dict()
    return run_admin_action(lambda: update_class(class_id, form_data), "Đã cập nhật lớp học phần.",
                            "academic.class_list_page", "update_class", "class")


# ---------- Đăng ký học ----------
@academic_bp.route("/classes/<int:class_id>/enrollments")
@admin_required
def enrollment_list_page(class_id):
    class_record = get_class_by_id(class_id)
    if class_record is None:
        abort(404)
    enrolled_ids = {item["student_id"] for item in get_enrollment_list(class_id)}
    available_students = [item for item in get_student_list() if item["student_id"] not in enrolled_ids]
    return render_template(
        "admin/academic/enrollments.html", class_record=class_record,
        enrollments=get_enrollment_list(class_id), available_students=available_students,
    )


@academic_bp.route("/classes/<int:class_id>/enrollments/update", methods=["POST"])
@admin_required
def enrollment_update_action(class_id):
    """Form gửi enrollment_action = add | remove và student_id."""
    enrollment_action = request.form.get("enrollment_action")
    try:
        student_id = int(request.form.get("student_id", ""))
    except ValueError:
        flash("Chưa chọn sinh viên.", "danger")
        return redirect(url_for("academic.enrollment_list_page", class_id=class_id))
    if enrollment_action == "add":
        def action_function():
            add_student_to_class(class_id, student_id)
            return {}
        message, log_action = "Đã thêm sinh viên vào lớp.", "add_student_to_class"
    elif enrollment_action == "remove":
        def action_function():
            remove_student_from_class(class_id, student_id)
            return {}
        message, log_action = "Đã xóa sinh viên khỏi lớp.", "remove_student_from_class"
    else:
        abort(400)
    return run_admin_action(action_function, message, "academic.enrollment_list_page",
                            log_action, "enrollment", class_id=class_id)
