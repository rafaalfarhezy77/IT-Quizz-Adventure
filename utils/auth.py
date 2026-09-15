from functools import wraps
from flask import g, jsonify, redirect, request, session, url_for
from models import Admin, db


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        admin = getattr(g, "current_admin", None)
        if admin is None:
            admin_id = session.get("admin_id")
            if admin_id:
                admin = db.session.get(Admin, admin_id)
                g.current_admin = admin
        if admin is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped_view
