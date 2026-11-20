"""Khởi tạo ứng dụng Flask cho Student Attendance System."""
from flask import Flask, flash, redirect, render_template, request, url_for

from config import Config
from app.models.database import init_account_system_tables
from app.models.notification import get_unread_notification_count
from app.models.user import get_current_user, seed_admin_from_env
from app.routes.activity_log import activity_log_bp
from app.routes.admin_users import admin_users_bp
from app.routes.auth import auth_bp
from app.routes.notification import notification_bp


def _register_optional_team_blueprints(app):
    """Tự động nạp thêm blueprint của các module khác nếu đã có trong nhánh hiện tại."""
    optional_modules = (
        ("app.models.academic", "init_academic_tables", "app.routes.academic", "academic_bp"),
        (None, None, "app.routes.schedule", "schedule_bp"),
    )
    for model_path, init_func_name, route_path, bp_name in optional_modules:
        if model_path and init_func_name:
            try:
                model_module = __import__(model_path, fromlist=[init_func_name])
                getattr(model_module, init_func_name)()
            except Exception:
                pass
        try:
            route_module = __import__(route_path, fromlist=[bp_name])
            blueprint = getattr(route_module, bp_name)
            app.register_blueprint(blueprint)
        except ImportError:
            pass


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
        seed_admin_from_env()
        _register_optional_team_blueprints(app)

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
            "has_endpoint": lambda endpoint_name: endpoint_name in app.view_functions,
        }

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
