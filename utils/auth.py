from functools import wraps
from flask import g, jsonify, redirect, request, session, url_for
from models import Admin, db


def resolve_current_admin():
    admin_id = session.get("admin_id")
    admin = db.session.get(Admin, admin_id) if isinstance(admin_id, int) else None
    if admin is not None and not admin.is_active:
        admin = None
    g.current_admin = admin
    return admin


def clear_auth_session():
    owner = session.get("demo_owner")
    session.clear()
    if owner:
        session["demo_owner"] = owner


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        admin = resolve_current_admin()
        if admin is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped_view
