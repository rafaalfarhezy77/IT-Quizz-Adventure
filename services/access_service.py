"""Database-backed public access policy, read anew on each request."""
from flask import current_app, g
from sqlalchemy.dialects.sqlite import insert
from models import WebsiteAccess, WebsiteAccessAudit, CompetitionSession, SessionStatus, db


def public_mode():
    return db.session.scalar(db.select(WebsiteAccess.mode).where(WebsiteAccess.id == 1)) or "NORMAL"


def demo_enabled():
    return public_mode() == "DEMO_ONLY" or bool(current_app.config.get("DEMO_ENABLED"))


def lock_access_settings():
    # Same write lock is used by official session starts and policy changes.
    db.session.execute(insert(WebsiteAccess).values(id=1, mode="NORMAL", lock_version=0).on_conflict_do_nothing())
    db.session.execute(db.update(WebsiteAccess).where(WebsiteAccess.id == 1)
                       .values(lock_version=WebsiteAccess.lock_version + 1))


def set_public_mode(mode, admin_id):
    if mode not in ("NORMAL", "DEMO_ONLY"):
        raise ValueError("Mode akses tidak valid.")
    lock_access_settings()
    previous = public_mode()
    if mode == "DEMO_ONLY" and previous != mode:
        running = db.session.scalar(db.select(CompetitionSession.id)
                                    .where(CompetitionSession.status == SessionStatus.RUNNING).limit(1))
        if running:
            db.session.rollback()
            raise ValueError("Selesaikan atau batalkan semua sesi lomba RUNNING sebelum mengaktifkan Masa Demo.")
    if previous != mode:
        db.session.execute(db.update(WebsiteAccess).where(WebsiteAccess.id == 1).values(mode=mode))
        db.session.add(WebsiteAccessAudit(admin_id=admin_id, previous_mode=previous, new_mode=mode))
    db.session.commit()
