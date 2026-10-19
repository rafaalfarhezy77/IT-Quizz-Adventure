"""Routes for Safe Exam Browser (SEB) configuration download, direct launch, and guidance."""
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from services.seb_service import (
    build_seb_plist,
    is_seb_enforced,
    is_seb_request,
    set_seb_enforced,
)
from utils.auth import admin_required

seb_bp = Blueprint("seb", __name__, url_prefix="/seb")


def _resolve_start_url() -> str:
    """Determine the participant start URL based on current host or configuration."""
    custom_url = request.args.get("start_url", "").strip()
    if custom_url and (custom_url.startswith("http://") or custom_url.startswith("https://")):
        return custom_url
    base = request.url_root.rstrip("/")
    return f"{base}{url_for('participant.access')}"


def _resolve_quit_url() -> str:
    """Determine the quit/exit URL for Safe Exam Browser."""
    base = request.url_root.rstrip("/")
    return f"{base}{url_for('index')}"


def _get_seb_protocol_url() -> str:
    """Generate the seb:// or sebs:// URL to trigger automatic launch in Safe Exam Browser."""
    config_url = f"{request.url_root.rstrip('/')}{url_for('seb.config_file')}"
    if config_url.startswith("https://"):
        return "sebs://" + config_url[len("https://"):]
    elif config_url.startswith("http://"):
        return "seb://" + config_url[len("http://"):]
    return config_url


@seb_bp.get("/config.seb")
def config_file():
    """Serve the dynamic .seb XML configuration file for SEB protocol launch and direct loading."""
    start_url = _resolve_start_url()
    quit_url = _resolve_quit_url()
    quit_password = current_app.config.get("SEB_QUIT_PASSWORD")
    allow_reload = current_app.config.get("SEB_ALLOW_RELOAD", True)

    xml_data = build_seb_plist(
        start_url=start_url,
        quit_url=quit_url,
        quit_password=quit_password,
        allow_reload=allow_reload,
    )
    return Response(
        xml_data,
        mimetype="application/x-seb",
        headers={
            "Content-Disposition": 'inline; filename="IT_Quizz_Adventure.seb"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@seb_bp.get("/download")
def download():
    """Force download the .seb configuration file to the participant workstation."""
    start_url = _resolve_start_url()
    quit_url = _resolve_quit_url()
    quit_password = current_app.config.get("SEB_QUIT_PASSWORD")
    allow_reload = current_app.config.get("SEB_ALLOW_RELOAD", True)

    xml_data = build_seb_plist(
        start_url=start_url,
        quit_url=quit_url,
        quit_password=quit_password,
        allow_reload=allow_reload,
    )
    return Response(
        xml_data,
        mimetype="application/x-seb",
        headers={
            "Content-Disposition": 'attachment; filename="IT_Quizz_Adventure.seb"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@seb_bp.get("/instruction")
def instruction():
    """Display comprehensive instructions for students and panitia on using Safe Exam Browser."""
    start_url = _resolve_start_url()
    seb_link = _get_seb_protocol_url()
    enforced = is_seb_enforced()
    in_seb = is_seb_request(request)
    return render_template(
        "seb/instruction.html",
        start_url=start_url,
        seb_link=seb_link,
        enforced=enforced,
        in_seb=in_seb,
    )


@seb_bp.post("/toggle-enforcement")
@admin_required
def toggle_enforcement():
    """Toggle the SEB enforcement requirement at runtime (Admin only)."""
    current_state = is_seb_enforced()
    new_state = not current_state
    set_seb_enforced(new_state)
    msg = (
        "Proteksi Safe Exam Browser (SEB) kini DIWAJIBKAN untuk seluruh peserta."
        if new_state
        else "Proteksi Safe Exam Browser (SEB) dinonaktifkan (mode fleksibel / perizinan browser biasa)."
    )
    flash(msg, "success" if new_state else "warning")
    next_url = request.form.get("next") or request.referrer or url_for("admin.dashboard")
    return redirect(next_url)
