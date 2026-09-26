import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'instance' / 'competition.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 15},
        "pool_pre_ping": True,
    }
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    TEMPLATES_AUTO_RELOAD = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    PARTICIPANT_ACCESS_CODE = os.environ.get("PARTICIPANT_ACCESS_CODE", "QUEST2026")
    TIME_BONUS_PER_SECOND = float(os.environ.get("TIME_BONUS_PER_SECOND", "1.0"))
    NETWORKING_STAGE_1_SECONDS = int(os.environ.get("NETWORKING_STAGE_1_SECONDS", "600"))
    NETWORKING_STAGE_2_SECONDS = int(os.environ.get("NETWORKING_STAGE_2_SECONDS", "300"))
    NETWORKING_STAGE_3_SECONDS = int(os.environ.get("NETWORKING_STAGE_3_SECONDS", "900"))
    MEMBER_ROTATION_COUNT = int(os.environ.get("MEMBER_ROTATION_COUNT", "3"))
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max request payload
