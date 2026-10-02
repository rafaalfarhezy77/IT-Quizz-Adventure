from pathlib import Path

from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from models import db

csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_app(config_class=Config):
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
        static_url_path="/static",
    )
    app.config.from_object(config_class)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    # Apply demo request limits before CSRF parses form bodies.
    @app.before_request
    def demo_boundaries():
        from flask import abort, request, jsonify
        from services.access_service import public_mode
        from utils.auth import resolve_current_admin
        from utils.participant_session import clear_participant_session
        mode = public_mode()
        admin = resolve_current_admin()
        allowed = request.endpoint in ("index", "static", "admin.login", "api.health", "participant.health") or request.blueprint == "demo"
        if mode == "DEMO_ONLY" and not admin and not allowed and request.endpoint:
            clear_participant_session()
            if request.blueprint == "api" or request.method != "GET" or request.is_json:
                return jsonify(error="competition_access_locked", message="Akses lomba belum dibuka selama masa demo."), 403
            return render_template("demo/locked.html", demo_mode=True), 403
        if request.path.startswith("/demo/"):
            request.max_content_length = app.config["DEMO_MAX_REQUEST_BYTES"]
        if request.blueprint in ("participant", "api"):
            values = [request.args, request.form]
            if request.is_json:
                payload = request.get_json(silent=True)
                if isinstance(payload, dict):
                    values.append(payload)
            for value in values:
                if value.get("mode") == "demo" or any(
                    str(value.get(key, "")).startswith("demo_")
                    for key in ("session_id", "submission_id", "attempt_id", "identifier", "team_id")
                ):
                    abort(403)
    csrf.init_app(app)

    # Pastikan folder instance dan uploads tersedia
    upload_dir = Path(app.config.get("UPLOAD_FOLDER", Path(app.instance_path) / "uploads")) / "hardware"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Jalankan migrasi dan penambahan skema baru secara aman & idempotent
    from migrations.upgrade_schema import upgrade_database_schema
    upgrade_database_schema(app)

    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.participant import participant_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(api_bp)
    from routes.demo import demo_bp
    app.register_blueprint(demo_bp)
    from services.demo_service import initialize
    with app.app_context():
        from services.access_service import demo_enabled
        if demo_enabled():
            initialize()

    @app.context_processor
    def access_context():
        from services.access_service import public_mode, demo_enabled
        from utils.auth import resolve_current_admin
        return {"public_access_mode": public_mode(), "demo_available": demo_enabled(),
                "access_admin": resolve_current_admin()}

    @app.errorhandler(400)
    @app.errorhandler(413)
    def demo_request_error(error):
        from flask import request, jsonify
        if request.blueprint == "demo":
            message = "Request terlalu besar." if error.code == 413 else "Request atau token keamanan tidak valid. Muat ulang halaman lalu coba lagi."
            if request.is_json:
                return jsonify(success=False, error=message), error.code
            return render_template("demo/page.html", demo_mode=True, page="error", message=message), error.code
        return error

    @app.cli.command("cleanup-demo")
    def cleanup_demo():
        """Delete expired practice attempts from the separate demo store."""
        from services.demo_service import cleanup, initialize
        initialize()
        print(f"Deleted {cleanup()} expired demo attempts.")

    from flask import send_from_directory

    @app.get("/uploads/hardware/<path:filename>")
    def uploaded_hardware_file(filename):
        safe_dir = Path(app.config.get("UPLOAD_FOLDER", Path(app.instance_path) / "uploads")) / "hardware"
        return send_from_directory(str(safe_dir), filename)

    @app.get("/")
    def index():
        return render_template("landing.html")

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("errors/500.html"), 500

    return app
