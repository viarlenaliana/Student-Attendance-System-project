"""Khởi tạo ứng dụng Flask cho Student Attendance System."""
import importlib
from flask import Flask, abort, flash, redirect, render_template, request, url_for

from config import Config
from app.models.database import init_account_system_tables
from app.models.notification import get_unread_notification_count
from app.models.user import get_current_user, seed_admin_from_env
from app.routes.activity_log import activity_log_bp
from app.routes.admin_users import admin_users_bp
from app.routes.auth import auth_bp
from app.routes.notification import notification_bp
from app.utils.csrf import CSRF_PROTECTED_BLUEPRINTS, generate_csrf_token, validate_csrf_token


def _register_optional_team_blueprints(app):
    """Nạp và đăng ký các Blueprint tích hợp từ module khác (Academic, Schedule) có ghi log rõ ràng."""
    optional_modules = (
        ("Academic", "app.models.academic", "init_academic_tables", "app.routes.academic", "academic_bp"),
        ("Schedule", None, None, "app.routes.schedule", "schedule_bp"),
    )
    for module_label, model_path, init_func_name, route_path, bp_name in optional_modules:
        if model_path and init_func_name:
            try:
                model_module = importlib.import_module(model_path)
                init_function = getattr(model_module, init_func_name)
                init_function()
            except ModuleNotFoundError as error:
                if error.name == model_path:
                    app.logger.info("Module %s (%s) chưa có trong nhánh hiện tại; bỏ qua khởi tạo bảng.", module_label, model_path)
                else:
                    app.logger.exception("Lỗi thiếu thư viện khi nạp model %s (%s): %s", module_label, model_path, error)
            except Exception as error:
                app.logger.exception("Lỗi khi khởi tạo bảng cho module %s (%s): %s", module_label, model_path, error)

        try:
            route_module = importlib.import_module(route_path)
            blueprint = getattr(route_module, bp_name)
            if blueprint.name not in app.blueprints:
                app.register_blueprint(blueprint)
                app.logger.info("Đã đăng ký Blueprint %s (%s).", blueprint.name, route_path)
        except ModuleNotFoundError as error:
            if error.name == route_path:
                app.logger.info("Blueprint %s (%s) chưa có trong nhánh hiện tại; bỏ qua đăng ký.", module_label, route_path)
            else:
                app.logger.exception("Lỗi thiếu phụ thuộc khi nạp route %s (%s): %s", module_label, route_path, error)
        except Exception as error:
            app.logger.exception("Lỗi khi đăng ký Blueprint %s (%s): %s", module_label, route_path, error)


def create_app(test_config=None):
    """Factory function tạo và cấu hình ứng dụng Flask."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_users_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(activity_log_bp)

    with app.app_context():
        init_account_system_tables()
        app.logger.info("Đã khởi tạo các bảng hệ thống tài khoản, OTP, thông báo và activity log.")
        seed_admin_from_env()
        _register_optional_team_blueprints(app)

    app.logger.info("Danh sách Blueprint đã đăng ký: %s", list(app.blueprints.keys()))

    @app.before_request
    def verify_csrf_protection():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        protected_blueprints = app.config.get("CSRF_PROTECTED_BLUEPRINTS", CSRF_PROTECTED_BLUEPRINTS)
        if not app.config.get("CSRF_PROTECT_ALL_BLUEPRINTS", False) and request.blueprint not in protected_blueprints:
            return None

        submitted_token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not validate_csrf_token(submitted_token):
            app.logger.warning("Từ chối yêu cầu %s tới %s do thiếu hoặc sai CSRF token.", request.method, request.path)
            abort(400)
        return None

    @app.before_request
    def enforce_first_login_password_change():
        if request.endpoint in (None, "static", "auth.change_password_page", "auth.logout_action"):
            return None
        user = get_current_user()
        if user is not None and user.get("must_change_password"):
            flash("Bạn phải đổi mật khẩu mặc định ở lần đăng nhập đầu tiên trước khi sử dụng hệ thống.", "warning")
            return redirect(url_for("auth.change_password_page"))
        return None

    @app.context_processor
    def inject_global_template_context():
        user = get_current_user()
        unread_count = get_unread_notification_count(user["user_id"]) if user else 0
        return {
            "nav_user": user,
            "unread_notification_count": unread_count,
            "csrf_token": generate_csrf_token,
            "has_endpoint": lambda endpoint_name: endpoint_name in app.view_functions,
        }

    @app.errorhandler(400)
    def handle_bad_request(_error):
        return (
            render_template(
                "errors/error.html",
                status_code=400,
                message="Yêu cầu không hợp lệ hoặc phiên bảo mật (CSRF) đã hết hạn. Vui lòng tải lại trang và thử lại.",
            ),
            400,
        )

    @app.errorhandler(401)
    def handle_unauthorized(_error):
        return render_template("errors/error.html", status_code=401, message="Bạn cần đăng nhập để truy cập chức năng này."), 401

    @app.errorhandler(403)
    def handle_forbidden(_error):
        return render_template("errors/error.html", status_code=403, message="Bạn không có quyền truy cập chức năng này."), 403

    @app.errorhandler(404)
    def handle_not_found(_error):
        return render_template("errors/error.html", status_code=404, message="Không tìm thấy trang được yêu cầu."), 404

    return app
