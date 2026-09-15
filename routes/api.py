from flask import Blueprint, jsonify, make_response, request
from models import CompetitionSession, Group, SessionStatus, Station, SubmissionStatus, db
from services.quiz_service import (
    get_or_create_submission,
    get_submission_answers_map,
    save_answer,
)
from services.scoring_service import finalize_submission
from services.session_service import (
    find_participant_session,
    get_effective_status,
    get_remaining_seconds,
    get_server_now,
)
from utils.auth import admin_required
from utils.participant_session import get_participant_context

api_bp = Blueprint("api", __name__, url_prefix="/api")


def no_store_json(payload, status_code=200):
    """Helper to return JSON responses with strict no-store caching headers."""
    resp = make_response(jsonify(payload), status_code)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@api_bp.get("/health")
def health():
    db.session.execute(db.select(Station.id).limit(1))
    return {"database": "ok", "status": "ok"}


@api_bp.get("/foundation-summary")
def foundation_summary():
    return {
        "stations": db.session.scalar(db.select(db.func.count()).select_from(Station)),
        "groups": db.session.scalar(db.select(db.func.count()).select_from(Group)),
    }


@api_bp.get("/participant/session-status")
def participant_session_status():
    """
    Participant polling endpoint for session status and server-authoritative timer.
    Protected by participant context validation and strictly cache-disabled.
    """
    ctx = get_participant_context()
    if not ctx["authorized"] or not ctx["station"] or not ctx["group"] or not ctx["team"]:
        return no_store_json(
            {"status": "UNAUTHORIZED", "error": "participant_state_invalid"},
            403,
        )

    if not ctx["rules_accepted"]:
        return no_store_json(
            {"status": "RULES_NOT_ACCEPTED", "error": "rules_not_accepted"},
            403,
        )

    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        return no_store_json({
            "status": "WAITING",
            "session_found": False,
        })

    effective_status = get_effective_status(session_obj)
    remaining_seconds = get_remaining_seconds(session_obj)

    return no_store_json({
        "status": effective_status.value,
        "session_found": True,
        "session_id": session_obj.id,
        "duration_seconds": session_obj.duration_seconds,
        "remaining_seconds": remaining_seconds,
        "server_time": get_server_now().isoformat(),
        "started_at": session_obj.started_at.isoformat() if session_obj.started_at else None,
    })


@api_bp.get("/admin/sessions/<int:session_id>/status")
@admin_required
def admin_session_status(session_id: int):
    """
    Admin polling endpoint for live session detail timer synchronization.
    Requires admin authentication and uses strict no-store headers.
    """
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        return no_store_json({"error": "Sesi perlombaan tidak ditemukan."}, 404)

    effective_status = get_effective_status(session_obj)
    remaining_seconds = get_remaining_seconds(session_obj)

    return no_store_json({
        "session_id": session_obj.id,
        "status": effective_status.value,
        "duration_seconds": session_obj.duration_seconds,
        "remaining_seconds": remaining_seconds,
        "server_time": get_server_now().isoformat(),
        "started_at": session_obj.started_at.isoformat() if session_obj.started_at else None,
        "ended_at": session_obj.ended_at.isoformat() if session_obj.ended_at else None,
    })


@api_bp.post("/participant/answer")
def participant_save_answer():
    """
    Endpoint autosave jawaban kuis peserta (AJAX / Fetch).
    Dilindungi validasi sesi peserta, CSRF, dan pengecekan deadline server.
    """
    ctx = get_participant_context()
    if not ctx["authorized"] or not ctx["station"] or not ctx["group"] or not ctx["team"]:
        return no_store_json({"error": "Akses peserta tidak valid."}, 403)

    if not ctx["rules_accepted"]:
        return no_store_json({"error": "Aturan pos belum disetujui."}, 403)

    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        return no_store_json({"error": "Tidak ada sesi lomba yang aktif."}, 400)

    effective_status = get_effective_status(session_obj)
    if effective_status != SessionStatus.RUNNING:
        return no_store_json(
            {"error": "Sesi lomba sudah selesai atau belum dimulai.", "status": effective_status.value},
            400,
        )

    remaining_seconds = get_remaining_seconds(session_obj)
    if remaining_seconds <= 0:
        submission = get_or_create_submission(session_obj.id, ctx["team"].id)
        finalize_submission(submission, is_timeout=True)
        return no_store_json(
            {"error": "Waktu pengerjaan telah habis.", "status": "TIMED_OUT"},
            400,
        )

    # Parsing payload (mendukung JSON maupun form-data)
    if request.is_json:
        payload = request.get_json() or {}
        raw_question_id = payload.get("question_id")
        raw_selected_answer = payload.get("selected_answer")
    else:
        raw_question_id = request.form.get("question_id")
        raw_selected_answer = request.form.get("selected_answer")

    try:
        question_id = int(raw_question_id)
    except (TypeError, ValueError):
        return no_store_json({"error": "ID soal tidak valid."}, 400)

    if not raw_selected_answer or str(raw_selected_answer).strip().upper() not in ("A", "B", "C", "D"):
        return no_store_json({"error": "Pilihan jawaban harus A, B, C, atau D."}, 400)

    selected_answer = str(raw_selected_answer).strip().upper()

    submission = get_or_create_submission(session_obj.id, ctx["team"].id)
    if submission.status != SubmissionStatus.IN_PROGRESS:
        return no_store_json(
            {"error": "Jawaban tidak dapat diubah karena submission telah difinalisasi."},
            400,
        )

    success, error_msg = save_answer(submission, question_id, selected_answer)
    if not success:
        return no_store_json({"error": error_msg or "Gagal menyimpan jawaban."}, 400)

    answers_map = get_submission_answers_map(submission.id)

    return no_store_json({
        "success": True,
        "saved": True,
        "question_id": question_id,
        "selected_answer": selected_answer,
        "answered_count": len(answers_map),
    })


@api_bp.get("/participant/leaderboard")
def participant_leaderboard_api():
    """Endpoint API JSON klasemen kuis pos untuk live polling peserta."""
    ctx = get_participant_context()
    if not ctx["authorized"] or not ctx["station"] or not ctx["group"] or not ctx["team"]:
        return no_store_json({"error": "Akses peserta tidak valid."}, 403)

    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        return no_store_json({"error": "Tidak ada sesi lomba yang aktif."}, 404)

    from services.leaderboard_service import get_session_leaderboard

    data = get_session_leaderboard(session_obj.id)
    rows = []
    for r in data["ranked_rows"]:
        rows.append({
            "rank": r["rank"],
            "team_code": r["team_code"],
            "team_name": r["team_name"],
            "school": r["school"],
            "raw_score": r["raw_score"],
            "time_bonus": r["time_bonus"],
            "final_score": r["final_score"],
            "is_my_team": (r["team_id"] == ctx["team"].id),
            "status": r["status"],
        })

    return no_store_json({
        "station_name": session_obj.station.name,
        "group_code": session_obj.group.code,
        "total_teams": data["total_teams"],
        "completed_count": data["completed_count"],
        "rows": rows,
    })


@api_bp.get("/admin/sessions/<int:session_id>/monitoring")
@admin_required
def admin_session_monitoring_api(session_id: int):
    """Endpoint polling data monitoring progres tim pada sesi lomba untuk panitia."""
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        return no_store_json({"error": "Sesi tidak ditemukan."}, 404)

    from services.leaderboard_service import get_session_monitoring_data

    data = get_session_monitoring_data(session_obj)
    return no_store_json(data)
