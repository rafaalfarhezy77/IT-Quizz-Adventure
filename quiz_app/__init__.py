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
    csrf.init_app(app)

    # Migrasi otomatis kolom baru Question jika belum ada
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                res = conn.execute(db.text("PRAGMA table_info(questions);")).fetchall()
                if res:
                    existing_cols = {row[1] for row in res}
                    if "external_id" not in existing_cols:
                        conn.execute(db.text("ALTER TABLE questions ADD COLUMN external_id VARCHAR(64);"))
                    if "category" not in existing_cols:
                        conn.execute(db.text("ALTER TABLE questions ADD COLUMN category VARCHAR(100);"))
                    if "member_number" not in existing_cols:
                        conn.execute(db.text("ALTER TABLE questions ADD COLUMN member_number INTEGER;"))
                    conn.commit()
        except Exception:
            pass

    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.participant import participant_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(api_bp)

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
