from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash

from forms.admin import LoginForm
from forms.question import (
    CaseStudyForm,
    EmptyForm,
    QuestionForm,
    QuestionImportConfirmForm,
    QuestionJSONUploadForm,
    QuestionSetStatusForm,
)
from forms.hardware import HardwareReviewForm
from forms.package import (
    HardwarePackageForm,
    PackageActionForm,
    PackageMappingForm,
    QuizPackageForm,
)
from forms.session import SessionActionForm, SessionForm
from forms.team import TeamCSVUploadForm, TeamForm, TeamImportConfirmForm
from models import (
    Admin,
    Answer,
    ChallengePackage,
    CompetitionSession,
    Group,
    GroupPackageMapping,
    HardwareSubmission,
    HardwareSubmissionAudit,
    NetworkingSubmission,
    NetworkingSubmissionAudit,
    PackageStatus,
    Question,
    QuestionSet,
    QuestionSetStatus,
    Score,
    SessionStatus,
    Station,
    StationMode,
    Submission,
    SubmissionStatus,
    Team,
    db,
)
from services.hardware_service import review_hardware_submission
from services.package_mapping_service import (
    apply_by_group_mapping,
    apply_same_for_all_mapping,
    get_group_mappings_for_station,
)
from services.package_service import (
    create_package,
    delete_or_archive_package,
    duplicate_package,
    generate_next_package_code,
    get_package_by_id,
    get_packages_by_station,
    is_package_editable,
    is_package_used,
    set_package_status,
    sync_quiz_packages_for_station,
    update_package,
)
from services.leaderboard_service import (
    generate_results_csv,
    get_filtered_results,
    get_session_monitoring_data,
)
from services.csv_import import (
    cleanup_temp_file,
    execute_team_import,
    generate_csv_template,
    get_temp_file_path,
    parse_and_validate_team_csv,
    save_temp_csv,
)
from services.question_json_import import (
    cleanup_temp_file as cleanup_temp_json,
    execute_question_import,
    parse_and_validate_question_json,
    save_temp_json,
)
from services.question_service import (
    ensure_default_question_sets,
    get_next_order_number,
    is_order_number_taken,
    is_question_set_editable,
    validate_question_set_ready,
)
from services.session_service import (
    cancel_session,
    clear_session_history,
    create_session,
    delete_session,
    finish_session,
    get_effective_status,
    get_remaining_seconds,
    start_session,
    update_session,
)
from utils.auth import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/leaderboard/global/display")
@admin_required
def global_leaderboard_display():
    return render_template("admin/leaderboard_display.html")


@admin_bp.before_request
def load_current_admin():
    g.current_admin = None
    admin_id = session.get("admin_id")
    if admin_id is None:
        return None
    admin = db.session.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        session.clear()
        flash("Sesi admin tidak valid. Silakan login kembali.", "warning")
        return redirect(url_for("admin.login"))
    g.current_admin = admin

    # Context pos aktif yang sedang dikelola admin
    station_id = session.get("admin_station_id")
    if station_id and station_id != 0:
        st = db.session.get(Station, station_id)
        g.active_station = st if (st and st.is_active) else None
    else:
        g.active_station = None

    # Wajib pilih pos setelah login jika belum menentukan pos atau mode global:
    allowed_endpoints = {
        "admin.station_select",
        "admin.set_station",
        "admin.clear_station",
        "admin.login",
        "admin.logout",
    }
    if not current_app.testing and "admin_station_id" not in session and request.endpoint and request.endpoint.startswith("admin."):
        if request.endpoint not in allowed_endpoints:
            flash("Silakan pilih pos lomba yang ingin dikelola terlebih dahulu.", "info")
            return redirect(url_for("admin.station_select"))

    return None


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.current_admin is not None:
        return redirect(url_for("admin.station_select"))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        admin = db.session.scalar(db.select(Admin).where(Admin.username == username))
        if admin and admin.is_active and check_password_hash(admin.password_hash, form.password.data):
            session.clear()
            session["admin_id"] = admin.id
            flash("Login berhasil. Silakan pilih pos lomba yang akan dikelola.", "success")
            return redirect(url_for("admin.station_select"))
        flash("Username atau password salah.", "error")
    return render_template("admin/login.html", form=form)


@admin_bp.post("/logout")
@admin_required
def logout():
    session.clear()
    flash("Anda telah logout.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.get("/station-select")
@admin_required
def station_select():
    """Halaman pemilihan pos bagi admin untuk menentukan fokus operasional pos."""
    station_order = db.case(
        {"Software Engineering": 1, "Cyber Security": 2, "Hardware": 3, "Networking": 4},
        value=Station.name,
        else_=99,
    )
    stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(station_order, Station.id.asc())
    ).all()

    station_meta = []
    for st in stations:
        is_hw = (st.name.lower() == "hardware")
        is_net = (st.name.lower() == "networking")
        is_se = (st.name.lower() == "software engineering" or st.mode.value == "member_rotation")
        is_cyber = (st.name.lower() == "cyber security")

        if is_hw:
            pkg_cnt = db.session.scalar(db.select(db.func.count()).select_from(ChallengePackage).where(ChallengePackage.station_id == st.id)) or 0
            pending_cnt = db.session.scalar(
                db.select(db.func.count())
                .select_from(HardwareSubmission)
                .join(Submission)
                .join(CompetitionSession)
                .where(CompetitionSession.station_id == st.id, HardwareSubmission.verification_status.in_(("SUBMITTED", "NEEDS_REVIEW")))
            ) or 0
            act_sess = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st.id, CompetitionSession.status == SessionStatus.RUNNING)) or 0
            meta = {
                "station": st,
                "type": "Hardware PC Challenge",
                "badge": "BuildCores PC Challenge",
                "badge_class": "badge-cyan",
                "card_class": "card-cyan",
                "icon": "💻",
                "desc": "Tantangan simulasi rakit PC via BuildCores dengan skenario kasus, batasan anggaran, dan penilaian spesifikasi.",
                "work_method": "Peserta merakit PC di BuildCores sesuai budget & kriteria, menginput form spek/harga, mengunggah bukti screenshot, lalu diverifikasi oleh juri.",
                "question_method": "Bukan kuis PG! Menggunakan Paket Studi Kasus Hardware (form target max budget, skor CPU/GPU, parts wajib/larangan).",
                "packages_count": pkg_cnt,
                "packages_label": "Paket Studi Kasus",
                "pending_count": pending_cnt,
                "active_sessions": act_sess,
                "is_hardware": True,
                "is_networking": False,
            }
        elif is_net:
            act_sess = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st.id, CompetitionSession.status == SessionStatus.RUNNING)) or 0
            pending_cnt = db.session.scalar(
                db.select(db.func.count())
                .select_from(Answer)
                .join(Submission, Answer.submission_id == Submission.id)
                .join(CompetitionSession, Submission.session_id == CompetitionSession.id)
                .where(CompetitionSession.station_id == st.id, Answer.review_status == "NEEDS_REVIEW")
            ) or 0
            q_cnt = db.session.scalar(db.select(db.func.count()).select_from(QuestionSet).where(QuestionSet.station_id == st.id)) or 0
            meta = {
                "station": st,
                "type": "Networking 3-Tahap",
                "badge": "Signal Check & Stamp",
                "badge_class": "badge-neon",
                "card_class": "card-white",
                "icon": "🌐",
                "desc": "Kuis tim multi-tahap (Signal Check, True or Trap, Case Signal) dengan konsol live monitoring dan verifikasi stamp.",
                "work_method": "Peserta mengerjakan kuis 3 tahap bertingkat. Jawaban kasus jaringan diverifikasi panitia untuk mendapatkan Stamp kelulusan tahap.",
                "question_method": "Bank Soal 3-Tahap Jaringan (pilihan ganda bertahap & isian studi kasus jaringan) via Bank Soal atau Import JSON.",
                "packages_count": q_cnt,
                "packages_label": "Bank Soal 3-Tahap",
                "pending_count": pending_cnt,
                "active_sessions": act_sess,
                "is_hardware": False,
                "is_networking": True,
            }
        elif is_se:
            q_cnt = db.session.scalar(db.select(db.func.count()).select_from(QuestionSet).where(QuestionSet.station_id == st.id)) or 0
            act_sess = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st.id, CompetitionSession.status == SessionStatus.RUNNING)) or 0
            meta = {
                "station": st,
                "type": "Software Engineering",
                "badge": "Rotasi Anggota Tim",
                "badge_class": "badge-yellow",
                "card_class": "card-yellow",
                "icon": "⚙️",
                "desc": "Kuis pemrograman & rekayasa perangkat lunak interaktif dengan aturan rotasi giliran anggota tim per butir/set soal.",
                "work_method": "Peserta menjawab soal dengan giliran bergantian antar anggota tim sesuai putaran rotasi sesi.",
                "question_method": "Bank Soal Kuis PG (Set A–D) pilihan ganda A–E, bobot poin, kunci jawaban, dan sinkronisasi nomor rotasi.",
                "packages_count": q_cnt,
                "packages_label": "Set Soal Rotasi",
                "pending_count": 0,
                "active_sessions": act_sess,
                "is_hardware": False,
                "is_networking": False,
            }
        else:
            q_cnt = db.session.scalar(db.select(db.func.count()).select_from(QuestionSet).where(QuestionSet.station_id == st.id)) or 0
            act_sess = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st.id, CompetitionSession.status == SessionStatus.RUNNING)) or 0
            meta = {
                "station": st,
                "type": "Cyber Security",
                "badge": "Kuis Standar Tim",
                "badge_class": "badge-black",
                "card_class": "card-white",
                "icon": "🛡️",
                "desc": "Kuis keamanan siber pilihan ganda interaktif yang dikerjakan secara kolaboratif bersama seluruh anggota tim.",
                "work_method": "Pengerjaan kuis pilihan ganda kolaboratif oleh seluruh anggota tim secara serentak.",
                "question_method": "Bank Soal Kuis PG (Set A–D) pilihan ganda A–E, bobot nilai, kunci jawaban, serta import JSON.",
                "packages_count": q_cnt,
                "packages_label": "Set Soal Kuis",
                "pending_count": 0,
                "active_sessions": act_sess,
                "is_hardware": False,
                "is_networking": False,
            }
        station_meta.append(meta)

    # Telemetri agregat untuk Mode Global (Pilihan ke-5)
    total_active_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.status == SessionStatus.RUNNING)) or 0
    total_teams_count = db.session.scalar(db.select(db.func.count()).select_from(Team).where(Team.is_active.is_(True))) or 0

    global_meta = {
        "total_active_sessions": total_active_sessions,
        "total_teams_count": total_teams_count,
    }

    return render_template("admin/station_select.html", station_meta=station_meta, global_meta=global_meta)


@admin_bp.get("/set-station/<int:station_id>")
@admin_required
def set_station(station_id: int):
    """Mengatur pos aktif yang dikelola admin."""
    if station_id == 0:
        session["admin_station_id"] = 0
        flash("Mode operasional diatur ke: Mode Global (Semua Pos).", "info")
        return redirect(url_for("admin.dashboard"))

    st = db.session.get(Station, station_id)
    if not st or not st.is_active:
        flash("Pos tidak ditemukan atau sedang tidak aktif.", "danger")
        return redirect(url_for("admin.station_select"))

    session["admin_station_id"] = st.id
    flash(f"Berhasil masuk ke: Pos {st.name}.", "success")
    if st.name.lower() == "networking":
        return redirect(url_for("admin.networking_lobby"))
    elif st.name.lower() == "hardware":
        return redirect(url_for("admin.dashboard"))
    else:
        return redirect(url_for("admin.dashboard"))


@admin_bp.get("/set-station/clear")
@admin_required
def clear_station():
    """Menghapus pilihan pos aktif dan kembali ke halaman pemilihan pos."""
    session.pop("admin_station_id", None)
    flash("Silakan pilih pos lomba yang ingin dikelola.", "info")
    return redirect(url_for("admin.station_select"))


@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    all_stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())
    ).all()
    st_active = g.active_station

    all_sessions = db.session.scalars(db.select(CompetitionSession)).all()
    unmapped_sessions = 0
    for s in all_sessions:
        if not s.package_id:
            from services.package_mapping_service import get_assigned_package_for_group
            pkg = get_assigned_package_for_group(s.station_id, s.group_id, s.id)
            if not pkg and (s.station.name.lower() == "hardware"):
                if not st_active or st_active.id == s.station_id:
                    unmapped_sessions += 1

    total_stations_count = db.session.scalar(db.select(db.func.count()).select_from(Station))
    total_groups_count = db.session.scalar(db.select(db.func.count()).select_from(Group))
    total_teams_count = db.session.scalar(db.select(db.func.count()).select_from(Team).where(Team.is_active.is_(True)))

    if st_active and st_active.name.lower() == "hardware":
        active_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st_active.id, CompetitionSession.status == SessionStatus.RUNNING)) or 0
        finished_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st_active.id, CompetitionSession.status == SessionStatus.FINISHED)) or 0
        total_subs = db.session.scalar(
            db.select(db.func.count())
            .select_from(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED)))
        ) or 0
        packages_count = db.session.scalar(db.select(db.func.count()).select_from(ChallengePackage).where(ChallengePackage.station_id == st_active.id)) or 0
        mapped_groups_count = db.session.scalar(db.select(db.func.count(db.func.distinct(GroupPackageMapping.group_id))).where(GroupPackageMapping.station_id == st_active.id)) or 0

        hw_draft = db.session.scalar(
            db.select(db.func.count())
            .select_from(HardwareSubmission)
            .join(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, HardwareSubmission.verification_status == "DRAFT")
        ) or 0
        hw_submitted = db.session.scalar(
            db.select(db.func.count())
            .select_from(HardwareSubmission)
            .join(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, HardwareSubmission.verification_status == "SUBMITTED")
        ) or 0
        hw_needs_review = db.session.scalar(
            db.select(db.func.count())
            .select_from(HardwareSubmission)
            .join(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, HardwareSubmission.verification_status == "NEEDS_REVIEW")
        ) or 0
        hw_verified = db.session.scalar(
            db.select(db.func.count())
            .select_from(HardwareSubmission)
            .join(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, HardwareSubmission.verification_status == "VERIFIED")
        ) or 0
        hw_rejected = db.session.scalar(
            db.select(db.func.count())
            .select_from(HardwareSubmission)
            .join(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, HardwareSubmission.verification_status == "REJECTED")
        ) or 0
        hw_scored = db.session.scalar(
            db.select(db.func.count())
            .select_from(HardwareSubmission)
            .join(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, HardwareSubmission.verification_status == "SCORED")
        ) or 0
        hw_pending = hw_submitted + hw_needs_review
        net_pending = net_finalized = net_stamps = 0
    elif st_active:
        active_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st_active.id, CompetitionSession.status == SessionStatus.RUNNING)) or 0
        finished_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.station_id == st_active.id, CompetitionSession.status == SessionStatus.FINISHED)) or 0
        total_subs = db.session.scalar(
            db.select(db.func.count())
            .select_from(Submission)
            .join(CompetitionSession)
            .where(CompetitionSession.station_id == st_active.id, Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED)))
        ) or 0
        packages_count = db.session.scalar(db.select(db.func.count()).select_from(QuestionSet).where(QuestionSet.station_id == st_active.id)) or 0
        mapped_groups_count = 4
        hw_draft = hw_submitted = hw_needs_review = hw_verified = hw_rejected = hw_scored = hw_pending = 0
        if st_active.name.lower() == "networking":
            net_pending = db.session.scalar(
                db.select(db.func.count())
                .select_from(NetworkingSubmission)
                .join(Submission)
                .join(CompetitionSession)
                .where(CompetitionSession.station_id == st_active.id, NetworkingSubmission.verification_status.in_(["SUBMITTED", "NEEDS_REVIEW"]))
            ) or 0
            net_finalized = db.session.scalar(
                db.select(db.func.count())
                .select_from(NetworkingSubmission)
                .join(Submission)
                .join(CompetitionSession)
                .where(CompetitionSession.station_id == st_active.id, NetworkingSubmission.verification_status == "FINALIZED")
            ) or 0
            net_stamps = db.session.scalar(
                db.select(db.func.count())
                .select_from(NetworkingSubmission)
                .join(Submission)
                .join(CompetitionSession)
                .where(CompetitionSession.station_id == st_active.id, NetworkingSubmission.has_stamp.is_(True))
            ) or 0
        else:
            net_pending = net_finalized = net_stamps = 0
    else:
        active_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.status == SessionStatus.RUNNING)) or 0
        finished_sessions = db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.status == SessionStatus.FINISHED)) or 0
        total_subs = db.session.scalar(db.select(db.func.count()).select_from(Submission).where(Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED)))) or 0
        packages_count = db.session.scalar(db.select(db.func.count()).select_from(ChallengePackage)) or 0
        mapped_groups_count = db.session.scalar(db.select(db.func.count(db.func.distinct(GroupPackageMapping.group_id)))) or 0
        hw_draft = db.session.scalar(db.select(db.func.count()).select_from(HardwareSubmission).where(HardwareSubmission.verification_status == "DRAFT")) or 0
        hw_submitted = db.session.scalar(db.select(db.func.count()).select_from(HardwareSubmission).where(HardwareSubmission.verification_status == "SUBMITTED")) or 0
        hw_needs_review = db.session.scalar(db.select(db.func.count()).select_from(HardwareSubmission).where(HardwareSubmission.verification_status == "NEEDS_REVIEW")) or 0
        hw_verified = db.session.scalar(db.select(db.func.count()).select_from(HardwareSubmission).where(HardwareSubmission.verification_status == "VERIFIED")) or 0
        hw_rejected = db.session.scalar(db.select(db.func.count()).select_from(HardwareSubmission).where(HardwareSubmission.verification_status == "REJECTED")) or 0
        hw_scored = db.session.scalar(db.select(db.func.count()).select_from(HardwareSubmission).where(HardwareSubmission.verification_status == "SCORED")) or 0
        hw_pending = hw_submitted + hw_needs_review
        net_pending = db.session.scalar(db.select(db.func.count()).select_from(NetworkingSubmission).where(NetworkingSubmission.verification_status.in_(["SUBMITTED", "NEEDS_REVIEW"]))) or 0
        net_finalized = db.session.scalar(db.select(db.func.count()).select_from(NetworkingSubmission).where(NetworkingSubmission.verification_status == "FINALIZED")) or 0
        net_stamps = db.session.scalar(db.select(db.func.count()).select_from(NetworkingSubmission).where(NetworkingSubmission.has_stamp.is_(True))) or 0

    statistics = {
        "stations": total_stations_count,
        "groups": total_groups_count,
        "teams": total_teams_count,
        "questions": db.session.scalar(db.select(db.func.count()).select_from(Question).where(Question.is_active.is_(True))),
        "active_sessions": active_sessions,
        "finished_sessions": finished_sessions,
        "total_submissions": total_subs,
        "packages": packages_count,
        "mapped_groups": mapped_groups_count,
        "unmapped_sessions": unmapped_sessions,
        "hw_draft": hw_draft,
        "hw_submitted": hw_submitted,
        "hw_needs_review": hw_needs_review,
        "hw_verified": hw_verified,
        "hw_rejected": hw_rejected,
        "hw_scored": hw_scored,
        "hw_pending": hw_pending,
        "net_pending": net_pending,
        "net_finalized": net_finalized,
        "net_stamps": net_stamps,
    }
    focus_sessions = [
        {
            "session": item,
            "status": get_effective_status(item),
            "remaining": get_remaining_seconds(item),
            "team_count": sum(1 for team in item.group.teams if team.is_active),
            "submitted_count": sum(1 for sub in item.submissions if sub.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED)),
        }
        for item in all_sessions
        if (not st_active or item.station_id == st_active.id)
        and item.status in (SessionStatus.WAITING, SessionStatus.RUNNING)
    ]
    focus_sessions.sort(key=lambda item: (item["status"] != SessionStatus.RUNNING, item["session"].station.name, item["session"].group.code))
    return render_template(
        "admin/dashboard.html",
        statistics=statistics,
        all_stations=all_stations,
        active_station=st_active,
        focus_sessions=focus_sessions,
    )


# ==============================================================================
# MANAJEMEN SOAL (LANGKAH 3)
# ==============================================================================

@admin_bp.get("/questions")
@admin_required
def questions_index():
    """Daftar seluruh question set dikelompokkan berdasarkan station aktif."""
    if g.active_station and g.active_station.name.lower() == "hardware":
        flash("Pos Hardware menggunakan sistem Paket Studi Kasus PC Challenge (bukan Bank Soal PG). Mengarahkan ke menu Paket Soal Hardware.", "info")
        return redirect(url_for("admin.packages_index", station_id=g.active_station.id))

    ensure_default_question_sets()

    selected_station_id = request.args.get("station_id", type=int)
    if g.active_station:
        selected_station_id = g.active_station.id

    station_priority = db.case(
        {"Software Engineering": 1, "Cyber Security": 2, "Hardware": 3, "Networking": 4},
        value=Station.name,
        else_=99,
    )
    station_query = (
        db.select(Station)
        .where(Station.is_active.is_(True))
        .order_by(station_priority, Station.id.asc())
    )
    all_stations = db.session.scalars(station_query).all()
    if not selected_station_id and all_stations:
        selected_station_id = all_stations[0].id

    if selected_station_id:
        stations = [s for s in all_stations if s.id == selected_station_id]
    else:
        stations = all_stations

    running_set_ids = set(db.session.scalars(
        db.select(CompetitionSession.question_set_id).where(CompetitionSession.status == SessionStatus.RUNNING)
    ).all())

    return render_template(
        "admin/questions/index.html",
        stations=stations,
        all_stations=all_stations,
        selected_station_id=selected_station_id,
        running_set_ids=running_set_ids,
    )


@admin_bp.route("/questions/set/<int:set_id>/case-study", methods=["GET", "POST"])
@admin_required
def question_set_case_study(set_id: int):
    question_set = db.session.get(QuestionSet, set_id, populate_existing=True)
    if question_set is None:
        abort(404)
    if g.active_station and question_set.station_id != g.active_station.id:
        abort(403)
    editable, reason = is_question_set_editable(question_set)
    if not editable:
        flash(reason, "error")
        return redirect(url_for("admin.questions_index", station_id=question_set.station_id))
    form = CaseStudyForm(data=question_set.case_study or {})
    if form.validate_on_submit():
        try:
            question_set.case_study = {"title": form.title.data.strip(), "description": form.description.data.strip()}
            db.session.commit()
            flash(f"Study case untuk Set {question_set.code} berhasil disimpan.", "success")
            return redirect(url_for("admin.questions_index", station_id=question_set.station_id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Gagal menyimpan studi kasus Set %s", set_id)
            flash("Study case gagal disimpan. Silakan coba kembali.", "error")
    return render_template("admin/questions/case_study_form.html", form=form, question_set=question_set)


@admin_bp.get("/questions/set/<int:set_id>")
@admin_required
def question_set_detail(set_id: int):
    """Detail satu question set, menampilkan daftar soal, filter, dan kontrol status."""
    question_set = db.session.get(QuestionSet, set_id)
    if question_set is None:
        abort(404)

    if g.active_station and question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Bank soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    status_filter = request.args.get("status", "all").strip().lower()
    search_query = request.args.get("search", "").strip()

    stmt = db.select(Question).where(Question.question_set_id == set_id)

    if status_filter == "active":
        stmt = stmt.where(Question.is_active.is_(True))
    elif status_filter == "inactive":
        stmt = stmt.where(Question.is_active.is_(False))

    if search_query:
        stmt = stmt.where(Question.text.ilike(f"%{search_query}%"))

    stmt = stmt.order_by(Question.order_number.asc(), Question.id.asc())
    questions = db.session.scalars(stmt).all()

    total_questions = len(question_set.questions)
    active_questions = sum(1 for q in question_set.questions if q.is_active)

    status_form = QuestionSetStatusForm(status=question_set.status.value)
    empty_form = EmptyForm()

    editable, locked_reason = is_question_set_editable(question_set)

    return render_template(
        "admin/questions/detail.html",
        question_set=question_set,
        questions=questions,
        total_questions=total_questions,
        active_questions=active_questions,
        status_filter=status_filter,
        search_query=search_query,
        status_form=status_form,
        empty_form=empty_form,
        editable=editable,
        locked_reason=locked_reason,
    )


@admin_bp.route("/questions/set/<int:set_id>/create", methods=["GET", "POST"])
@admin_required
def question_create(set_id: int):
    """Form penambahan soal baru ke dalam question set."""
    question_set = db.session.get(QuestionSet, set_id)
    if question_set is None:
        abort(404)

    if g.active_station and question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Bank soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    editable, reason = is_question_set_editable(question_set)
    if not editable:
        flash(reason or "Question set sedang dikunci dan tidak dapat diedit.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=set_id))

    form = QuestionForm()
    if request.method == "GET":
        form.order_number.data = get_next_order_number(set_id)
        form.weight.data = 100.0

    if form.validate_on_submit():
        if is_order_number_taken(set_id, form.order_number.data):
            form.order_number.errors.append(
                f"Nomor urut {form.order_number.data} sudah digunakan oleh soal lain dalam set ini."
            )
        else:
            try:
                question = Question(
                    question_set_id=set_id,
                    text=form.text.data.strip(),
                    option_a=form.option_a.data.strip(),
                    option_b=form.option_b.data.strip(),
                    option_c=form.option_c.data.strip(),
                    option_d=form.option_d.data.strip(),
                    correct_answer=form.correct_answer.data,
                    weight=float(form.weight.data),
                    order_number=int(form.order_number.data),
                    is_active=True,
                )
                db.session.add(question)
                db.session.commit()
                flash("Soal berhasil ditambahkan.", "success")
                return redirect(url_for("admin.question_set_detail", set_id=set_id))
            except Exception:
                db.session.rollback()
                flash("Terjadi kesalahan basis data saat menyimpan soal.", "error")

    return render_template(
        "admin/questions/form.html",
        form=form,
        question_set=question_set,
        is_edit=False,
    )


@admin_bp.route("/questions/<int:question_id>/edit", methods=["GET", "POST"])
@admin_required
def question_edit(question_id: int):
    """Form pengeditan soal existing."""
    question = db.session.get(Question, question_id)
    if question is None:
        abort(404)

    if g.active_station and question.question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    question_set = question.question_set
    editable, reason = is_question_set_editable(question_set)
    if not editable:
        flash(reason or "Question set sedang dikunci dan tidak dapat diedit.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question_set.id))

    form = QuestionForm(obj=question)

    if form.validate_on_submit():
        if is_order_number_taken(question_set.id, form.order_number.data, exclude_question_id=question.id):
            form.order_number.errors.append(
                f"Nomor urut {form.order_number.data} sudah digunakan oleh soal lain dalam set ini."
            )
        else:
            try:
                question.text = form.text.data.strip()
                question.option_a = form.option_a.data.strip()
                question.option_b = form.option_b.data.strip()
                question.option_c = form.option_c.data.strip()
                question.option_d = form.option_d.data.strip()
                question.correct_answer = form.correct_answer.data
                question.weight = float(form.weight.data)
                question.order_number = int(form.order_number.data)

                db.session.commit()
                flash("Soal berhasil diperbarui.", "success")
                return redirect(url_for("admin.question_set_detail", set_id=question_set.id))
            except Exception:
                db.session.rollback()
                flash("Terjadi kesalahan basis data saat memperbarui soal.", "error")

    return render_template(
        "admin/questions/form.html",
        form=form,
        question_set=question_set,
        question=question,
        is_edit=True,
    )


@admin_bp.post("/questions/set/<int:set_id>/bulk-delete")
@admin_required
def questions_bulk_delete(set_id: int):
    """Nonaktifkan atau hapus pilihan soal dalam satu transaksi."""
    question_set = db.session.get(QuestionSet, set_id)
    if question_set is None:
        abort(404)
    if g.active_station and question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Bank soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    status_filter = request.form.get("status", "all")
    if status_filter not in ("all", "active", "inactive"):
        status_filter = "all"
    destination = url_for("admin.question_set_detail", set_id=set_id,
                          status=status_filter, search=request.form.get("search", ""))
    if not EmptyForm().validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(destination)
    editable, reason = is_question_set_editable(question_set)
    if not editable:
        flash(reason or "Question set sedang dikunci.", "error")
        return redirect(destination)

    action = request.form.get("delete_mode", "deactivate")
    if action not in ("deactivate", "permanent"):
        flash("Pilihan penghapusan tidak valid.", "error")
        return redirect(destination)
    try:
        question_ids = {int(value) for value in request.form.getlist("question_ids")}
    except (ValueError, TypeError):
        flash("Pilihan soal tidak valid.", "error")
        return redirect(destination)
    if not question_ids:
        flash("Pilih minimal satu soal terlebih dahulu.", "error")
        return redirect(destination)
    questions = db.session.scalars(db.select(Question).where(
        Question.question_set_id == set_id, Question.id.in_(question_ids)
    )).all()
    if len(questions) != len(question_ids):
        flash("Pilihan soal tidak valid atau bukan milik paket ini. Tidak ada soal yang diubah.", "error")
        return redirect(destination)
    if action == "permanent" and any(question.answers for question in questions):
        flash("Penghapusan dibatalkan: ada soal dengan riwayat pengerjaan. Gunakan pilihan nonaktifkan soal.", "error")
        return redirect(destination)

    try:
        for question in questions:
            if action == "permanent":
                db.session.delete(question)
            else:
                question.is_active = False
        db.session.commit()
        result = "dihapus permanen" if action == "permanent" else "dinonaktifkan"
        flash(f"{len(questions)} soal berhasil {result}.", "success")
    except Exception:
        db.session.rollback()
        flash("Terjadi kesalahan basis data. Penghapusan soal dibatalkan.", "error")
    return redirect(destination)


@admin_bp.post("/questions/<int:question_id>/delete")
@admin_required
def question_delete(question_id: int):
    """Soft delete soal (is_active = False)."""
    question = db.session.get(Question, question_id)
    if question is None:
        abort(404)

    if g.active_station and question.question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    editable, reason = is_question_set_editable(question.question_set)
    if not editable:
        flash(reason or "Question set sedang dikunci dan tidak dapat dimodifikasi.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    try:
        question.is_active = False
        db.session.commit()
        flash("Soal berhasil dinonaktifkan.", "success")
    except Exception:
        db.session.rollback()
        flash("Terjadi kesalahan basis data saat menonaktifkan soal.", "error")

    return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))


@admin_bp.post("/questions/<int:question_id>/restore")
@admin_required
def question_restore(question_id: int):
    """Restore soal nonaktif (is_active = True)."""
    question = db.session.get(Question, question_id)
    if question is None:
        abort(404)

    if g.active_station and question.question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    editable, reason = is_question_set_editable(question.question_set)
    if not editable:
        flash(reason or "Question set sedang dikunci dan tidak dapat dimodifikasi.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    try:
        question.is_active = True
        db.session.commit()
        flash("Soal berhasil diaktifkan kembali.", "success")
    except Exception:
        db.session.rollback()
        flash("Terjadi kesalahan basis data saat mengaktifkan kembali soal.", "error")

    return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))


@admin_bp.post("/questions/<int:question_id>/permanent-delete")
@admin_required
def question_permanent_delete(question_id: int):
    """Hapus soal secara permanen dari database."""
    question = db.session.get(Question, question_id)
    if question is None:
        abort(404)

    if g.active_station and question.question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    editable, reason = is_question_set_editable(question.question_set)
    if not editable:
        flash(reason or "Question set sedang dikunci dan tidak dapat dimodifikasi.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    if question.answers and len(question.answers) > 0:
        flash("Soal tidak dapat dihapus permanen karena memiliki riwayat pengerjaan. Gunakan tombol nonaktifkan.", "error")
        return redirect(url_for("admin.question_set_detail", set_id=question.question_set_id))

    set_id = question.question_set_id
    order_num = question.order_number
    try:
        db.session.delete(question)
        db.session.commit()
        flash(f"Soal nomor #{order_num} berhasil dihapus permanen dari paket soal.", "success")
    except Exception:
        db.session.rollback()
        flash("Terjadi kesalahan basis data saat menghapus soal.", "error")

    return redirect(url_for("admin.question_set_detail", set_id=set_id))


@admin_bp.post("/questions/set/<int:set_id>/status")
@admin_required
def question_set_status(set_id: int):
    """Mengubah status question set (DRAFT, READY, LOCKED)."""
    question_set = db.session.get(QuestionSet, set_id)
    if question_set is None:
        abort(404)

    if g.active_station and question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Bank soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    form = QuestionSetStatusForm()
    if form.validate_on_submit():
        target_status = form.status.data

        if target_status == question_set.status.value:
            flash(f"Status question set sudah berstatus {target_status}.", "info")
            return redirect(url_for("admin.question_set_detail", set_id=set_id))

        # Validasi jika ingin mengubah ke READY
        if target_status == "READY":
            is_ready, reasons = validate_question_set_ready(question_set)
            if not is_ready:
                flash("Set belum dapat ditandai READY:", "error")
                for r in reasons:
                    flash(f"• {r}", "error")
                return redirect(url_for("admin.question_set_detail", set_id=set_id))

        # Cek apakah set sedang digunakan oleh sesi yang sedang berjalan (RUNNING)
        if target_status != "LOCKED":
            running_session = db.session.scalar(
                db.select(CompetitionSession).where(
                    CompetitionSession.question_set_id == question_set.id,
                    CompetitionSession.status == SessionStatus.RUNNING,
                )
            )
            if running_session is not None:
                flash(
                    f"Question set sedang digunakan pada Sesi #{running_session.id} yang sedang berlangsung. Selesaikan atau batalkan sesi terlebih dahulu sebelum mengubah status.",
                    "error",
                )
                return redirect(url_for("admin.question_set_detail", set_id=set_id))

        try:
            question_set.status = QuestionSetStatus(target_status)
            db.session.commit()
            flash(f"Status question set berhasil diubah menjadi {target_status}.", "success")
        except Exception:
            db.session.rollback()
            flash("Terjadi kesalahan basis data saat memperbarui status question set.", "error")
    else:
        flash("Data status tidak valid.", "error")

    return redirect(url_for("admin.question_set_detail", set_id=set_id))


@admin_bp.get("/questions/set/<int:set_id>/preview")
@admin_required
def question_set_preview(set_id: int):
    """Halaman preview soal dalam satu question set untuk admin."""
    question_set = db.session.get(QuestionSet, set_id)
    if question_set is None:
        abort(404)

    if g.active_station and question_set.station_id != g.active_station.id:
        flash("Akses ditolak. Bank soal ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.questions_index"))

    active_questions = [
        q for q in sorted(question_set.questions, key=lambda x: (x.order_number, x.id))
        if q.is_active
    ]

    return render_template(
        "admin/questions/preview.html",
        question_set=question_set,
        questions=active_questions,
    )


# ==============================================================================
# IMPORT BANK SOAL JSON
# ==============================================================================

@admin_bp.route("/questions/import", methods=["GET", "POST"])
@admin_required
def questions_import():
    """Upload dan validasi berkas JSON Bank Soal."""
    form = QuestionJSONUploadForm()
    if g.active_station:
        active_stations = [g.active_station]
        form.station_id.choices = [
            (g.active_station.id, f"{g.active_station.name} ({'BELUM DIKETAHUI' if g.active_station.mode == StationMode.BELUM_DIKETAHUI else g.active_station.mode.value})")
        ]
        if request.method == "GET":
            form.station_id.data = g.active_station.id
    else:
        active_stations = db.session.scalars(
            db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())
        ).all()
        form.station_id.choices = [
            (s.id, f"{s.name} ({'BELUM DIKETAHUI' if s.mode == StationMode.BELUM_DIKETAHUI else s.mode.value})")
            for s in active_stations
        ]

    if form.validate_on_submit():
        file = form.file.data
        station_id = form.station_id.data
        mode = form.mode.data
        filename = file.filename

        if not filename or not filename.lower().endswith(".json"):
            flash("Format berkas tidak valid. Silakan unggah berkas dengan ekstensi .json.", "error")
            return redirect(url_for("admin.questions_import"))

        file_token, temp_path = save_temp_json(file)
        validation = parse_and_validate_question_json(temp_path, station_id, mode)

        if not validation["success"]:
            cleanup_temp_json(file_token)
            err = " ".join(validation["global_errors"]) if validation["global_errors"] else "Gagal memproses file JSON."
            flash(err, "error")
            return redirect(url_for("admin.questions_import"))

        confirm_form = QuestionImportConfirmForm(
            file_token=file_token,
            station_id=str(station_id),
            mode=mode,
        )

        return render_template(
            "admin/questions/import_preview.html",
            file_token=file_token,
            filename=filename,
            station_id=station_id,
            mode=mode,
            validation=validation,
            confirm_form=confirm_form,
        )

    return render_template(
        "admin/questions/import.html",
        form=form,
        stations=active_stations,
    )


@admin_bp.post("/questions/import/confirm")
@admin_required
def questions_import_confirm():
    """Eksekusi import bank soal ke basis data secara atomik (All-or-Nothing)."""
    form = QuestionImportConfirmForm()
    if not form.validate_on_submit():
        flash("Sesi konfirmasi tidak valid atau token CSRF kedaluwarsa.", "error")
        return redirect(url_for("admin.questions_import"))

    file_token = form.file_token.data
    try:
        station_id = int(form.station_id.data)
    except (TypeError, ValueError):
        cleanup_temp_json(file_token)
        flash("ID Pos tidak valid.", "error")
        return redirect(url_for("admin.questions_import"))

    mode = form.mode.data or "ADD"
    success, stats, err_msg = execute_question_import(file_token, station_id, mode)

    if success:
        sets_str = ", ".join(f"Set {s}" for s in stats.get("affected_sets", []))
        ins = stats.get("inserted", 0)
        upd = stats.get("updated", 0)
        if mode == "UPDATE":
            flash(f"Import berhasil: {upd} soal diperbarui dan {ins} soal baru ditambahkan pada paket {sets_str}.", "success")
        else:
            flash(f"Import berhasil: {ins} butir soal baru berhasil ditambahkan pada paket {sets_str}.", "success")
        return redirect(url_for("admin.questions_index", station_id=station_id))
    else:
        flash(f"Import gagal: {err_msg}", "error")
        return redirect(url_for("admin.questions_import"))


@admin_bp.post("/questions/import/cancel")
@admin_required
def questions_import_cancel():
    """Batalkan proses import dan bersihkan berkas sementara."""
    file_token = request.form.get("file_token", "").strip()
    if file_token:
        cleanup_temp_json(file_token)
    flash("Proses import bank soal dibatalkan.", "info")
    return redirect(url_for("admin.questions_index"))


@admin_bp.get("/questions/sample.json")
@admin_required
def questions_sample_json():
    """Unduh berkas contoh bank_soal.json resmi."""
    sample_path = Path(current_app.root_path) / "bank_soal.json"
    if not sample_path.is_file():
        sample_path = Path("bank_soal.json")
    if sample_path.is_file():
        with open(sample_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(
            content,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=bank_soal.json"},
        )
    abort(404)



# ==============================================================================
# MANAJEMEN TIM & IMPORT CSV (LANGKAH 4)
# ==============================================================================

@admin_bp.get("/teams")
@admin_required
def teams_index():
    """Daftar seluruh tim peserta dengan pencarian dan filter group/status."""
    search_query = request.args.get("search", "").strip()
    selected_group_code = request.args.get("group", "").strip().upper()
    status_filter = request.args.get("status", "all").strip().lower()

    stmt = db.select(Team).join(Group)

    if search_query:
        search_pattern = f"%{search_query}%"
        stmt = stmt.where(
            db.or_(
                Team.team_code.ilike(search_pattern),
                Team.team_name.ilike(search_pattern),
                Team.school.ilike(search_pattern),
            )
        )

    if selected_group_code:
        stmt = stmt.where(Group.code == selected_group_code)

    if status_filter == "active":
        stmt = stmt.where(Team.is_active.is_(True))
    elif status_filter == "inactive":
        stmt = stmt.where(Team.is_active.is_(False))

    stmt = stmt.order_by(Group.code.asc(), Team.team_code.asc())
    teams = db.session.scalars(stmt).all()

    # Statistik tim
    total_teams = db.session.scalar(db.select(db.func.count()).select_from(Team))
    active_teams = db.session.scalar(db.select(db.func.count()).select_from(Team).where(Team.is_active.is_(True)))

    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()
    stations = db.session.scalars(db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())).all()

    # Hitung keikutsertaan / aktivitas tiap tim di seluruh pos lomba secara global
    team_ids = [t.id for t in teams]
    team_station_activity = {t.id: {} for t in teams}
    if team_ids:
        submissions = db.session.scalars(
            db.select(Submission)
            .options(
                joinedload(Submission.session).joinedload(CompetitionSession.station),
                joinedload(Submission.score),
            )
            .where(Submission.team_id.in_(team_ids))
        ).unique().all()
        for sub in submissions:
            if sub.session and sub.session.station:
                team_station_activity[sub.team_id][sub.session.station_id] = {
                    "status": sub.status.value,
                    "score": sub.score.final_score if sub.score else None,
                    "station_name": sub.session.station.name,
                }

    empty_form = EmptyForm()

    return render_template(
        "admin/teams/index.html",
        teams=teams,
        groups=groups,
        stations=stations,
        team_station_activity=team_station_activity,
        total_teams=total_teams,
        active_teams=active_teams,
        search_query=search_query,
        selected_group=selected_group_code,
        status_filter=status_filter,
        empty_form=empty_form,
    )


@admin_bp.route("/teams/create", methods=["GET", "POST"])
@admin_required
def team_create():
    """Tambah data tim secara manual."""
    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()
    form = TeamForm()
    form.group_id.choices = [(g.id, f"Group {g.code}") for g in groups]

    if form.validate_on_submit():
        normalized_code = form.team_code.data.strip().upper()
        
        # Validasi duplicate case-insensitive
        existing = db.session.scalar(
            db.select(Team).where(func.lower(Team.team_code) == normalized_code.lower())
        )
        if existing:
            form.team_code.errors.append(f"Kode tim '{normalized_code}' sudah terdaftar.")
        else:
            try:
                new_team = Team(
                    team_code=normalized_code,
                    team_name=form.team_name.data.strip(),
                    school=form.school.data.strip(),
                    group_id=form.group_id.data,
                    is_active=True,
                )
                db.session.add(new_team)
                db.session.commit()
                flash(f"Tim '{normalized_code}' ({new_team.team_name}) berhasil ditambahkan.", "success")
                return redirect(url_for("admin.teams_index"))
            except Exception:
                db.session.rollback()
                flash("Terjadi kesalahan basis data saat menambahkan tim.", "error")

    return render_template("admin/teams/form.html", form=form, is_edit=False)


@admin_bp.route("/teams/<int:team_id>/edit", methods=["GET", "POST"])
@admin_required
def team_edit(team_id: int):
    """Edit data tim manual."""
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)

    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()
    form = TeamForm(obj=team)
    form.group_id.choices = [(g.id, f"Group {g.code}") for g in groups]

    if form.validate_on_submit():
        normalized_code = form.team_code.data.strip().upper()

        # Validasi duplicate case-insensitive dengan tim lain
        existing = db.session.scalar(
            db.select(Team).where(
                func.lower(Team.team_code) == normalized_code.lower(),
                Team.id != team_id,
            )
        )
        if existing:
            form.team_code.errors.append(f"Kode tim '{normalized_code}' sudah digunakan oleh tim lain.")
        else:
            try:
                team.team_code = normalized_code
                team.team_name = form.team_name.data.strip()
                team.school = form.school.data.strip()
                team.group_id = form.group_id.data

                db.session.commit()
                flash(f"Data tim '{normalized_code}' berhasil diperbarui.", "success")
                return redirect(url_for("admin.teams_index"))
            except Exception:
                db.session.rollback()
                flash("Terjadi kesalahan basis data saat memperbarui data tim.", "error")

    return render_template("admin/teams/form.html", form=form, team=team, is_edit=True)


@admin_bp.post("/teams/<int:team_id>/deactivate")
@admin_required
def team_deactivate(team_id: int):
    """Soft delete / nonaktifkan tim."""
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)

    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.teams_index"))

    try:
        team.is_active = False
        db.session.commit()
        flash(f"Tim '{team.team_code}' berhasil dinonaktifkan.", "success")
    except Exception:
        db.session.rollback()
        flash("Terjadi kesalahan basis data saat menonaktifkan tim.", "error")

    return redirect(url_for("admin.teams_index"))


@admin_bp.post("/teams/delete-permanent")
@admin_required
def teams_delete_permanent():
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    reason = request.form.get("reason", "").strip()
    raw_ids = request.form.getlist("team_ids")
    if not reason or len(reason) > 500 or request.form.get("confirmation") != "HAPUS PERMANEN":
        flash("Isi alasan (maksimal 500 karakter) dan ketik HAPUS PERMANEN untuk konfirmasi.", "error")
        return redirect(url_for("admin.teams_index"))
    try:
        team_ids = {int(value) for value in raw_ids}
    except ValueError:
        abort(400)
    if not team_ids or any(value <= 0 for value in team_ids):
        flash("Pilih minimal satu tim yang akan dihapus.", "error")
        return redirect(url_for("admin.teams_index"))
    teams = db.session.scalars(db.select(Team).where(Team.id.in_(team_ids))).all()
    if len(teams) != len(team_ids):
        flash("Pilihan tim sudah berubah. Muat ulang dan pilih kembali.", "error")
        return redirect(url_for("admin.teams_index"))
    identities = [(team.id, team.team_code) for team in teams]
    try:
        for team in teams:
            for submission in list(team.submissions):
                if submission.score:
                    db.session.delete(submission.score)
                for answer in list(submission.answers):
                    db.session.delete(answer)
                db.session.delete(submission)
            db.session.flush()
            db.session.delete(team)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Gagal menghapus tim permanen")
        flash("Penghapusan gagal. Tidak ada tim yang dihapus.", "error")
        return redirect(url_for("admin.teams_index"))
    current_app.logger.warning("TEAM_PERMANENT_DELETE admin=%s teams=%s reason=%r", g.current_admin.id, identities, reason)
    flash(f"{len(teams)} tim beserta seluruh jawaban, nilai, dan riwayatnya telah dihapus permanen.", "success")
    return redirect(url_for("admin.teams_index"))


@admin_bp.post("/teams/<int:team_id>/restore")
@admin_required
def team_restore(team_id: int):
    """Pulihkan / aktifkan kembali tim."""
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)

    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.teams_index"))

    try:
        team.is_active = True
        db.session.commit()
        flash(f"Tim '{team.team_code}' berhasil diaktifkan kembali.", "success")
    except Exception:
        db.session.rollback()
        flash("Terjadi kesalahan basis data saat mengaktifkan kembali tim.", "error")

    return redirect(url_for("admin.teams_index"))


@admin_bp.route("/teams/import", methods=["GET", "POST"])
@admin_required
def teams_import():
    """Upload dan parsing preview file CSV tim."""
    form = TeamCSVUploadForm()

    if form.validate_on_submit():
        file = form.file.data
        filename = file.filename
        
        # Validasi ekstensi
        if not filename or not filename.lower().endswith(".csv"):
            flash("Format file tidak valid. Silakan unggah file dengan ekstensi .csv.", "error")
            return redirect(url_for("admin.teams_import"))

        file_token, temp_path = save_temp_csv(file)
        validation = parse_and_validate_team_csv(temp_path)

        if not validation["success"]:
            cleanup_temp_file(file_token)
            flash(validation.get("header_error") or "Gagal memproses file CSV.", "error")
            return redirect(url_for("admin.teams_import"))

        confirm_form = TeamImportConfirmForm(file_token=file_token)
        return render_template(
            "admin/teams/import_preview.html",
            file_token=file_token,
            filename=filename,
            validation=validation,
            confirm_form=confirm_form,
        )

    return render_template("admin/teams/import.html", form=form)


@admin_bp.post("/teams/import/confirm")
@admin_required
def teams_import_confirm():
    """Eksekusi import database secara atomik (All-or-Nothing)."""
    form = TeamImportConfirmForm()
    if not form.validate_on_submit():
        flash("Sesi konfirmasi tidak valid atau token CSRF kedaluwarsa.", "error")
        return redirect(url_for("admin.teams_import"))

    file_token = form.file_token.data
    success, imported_count, err_msg = execute_team_import(file_token)

    if success:
        flash(f"Import berhasil. {imported_count} tim berhasil ditambahkan ke sistem lomba.", "success")
        return redirect(url_for("admin.teams_index"))
    else:
        flash(f"Import gagal: {err_msg}", "error")
        return redirect(url_for("admin.teams_import"))


@admin_bp.post("/teams/import/cancel")
@admin_required
def teams_import_cancel():
    """Batalkan import dan bersihkan file sementara."""
    file_token = request.form.get("file_token", "").strip()
    if file_token:
        cleanup_temp_file(file_token)
    flash("Proses import tim dibatalkan.", "info")
    return redirect(url_for("admin.teams_index"))


@admin_bp.get("/teams/template.csv")
@admin_required
def teams_template_csv():
    """Unduh file template resmi CSV data tim."""
    csv_content = generate_csv_template()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=team_template.csv",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


# ==============================================================================
# MANAJEMEN SESI (LANGKAH 6)
# ==============================================================================

def _populate_session_form_choices(form, station_id=None):
    if g.active_station:
        st_active = g.active_station
        form.station_id.choices = [
            (st_active.id, f"{st_active.name} ({'BELUM DIKETAHUI' if st_active.mode == StationMode.BELUM_DIKETAHUI else st_active.mode.value})")
        ]
        if st_active.name.lower() == "hardware":
            form.question_set_id.choices = [(0, "Tanpa bank soal — khusus Hardware (paket studi kasus)")]
        else:
            ready_sets = db.session.scalars(
                db.select(QuestionSet)
                .where(QuestionSet.station_id == st_active.id, QuestionSet.status == QuestionSetStatus.READY)
                .order_by(QuestionSet.code)
            ).all()
            form.question_set_id.choices = [
                (qs.id, f"Set {qs.code} ({qs.name})") for qs in ready_sets
            ]
            if not form.question_set_id.choices:
                form.question_set_id.choices = [(0, "-- Belum ada bank soal READY pada pos ini --")]
    else:
        active_stations = db.session.scalars(
            db.select(Station).where(Station.is_active.is_(True)).order_by(Station.name)
        ).all()
        form.station_id.choices = [
            (s.id, f"{s.name} ({'BELUM DIKETAHUI' if s.mode == StationMode.BELUM_DIKETAHUI else s.mode.value})")
            for s in active_stations
        ]
        ready_sets = db.session.scalars(
            db.select(QuestionSet)
            .join(Station)
            .where(QuestionSet.status == QuestionSetStatus.READY)
            .order_by(Station.name, QuestionSet.code)
        ).all()
        form.question_set_id.choices = [(0, "Tanpa bank soal — khusus Hardware (paket studi kasus)")] + [
            (qs.id, f"{qs.station.name} — Set {qs.code} ({qs.name})") for qs in ready_sets
        ]

    groups = db.session.scalars(db.select(Group).order_by(Group.code)).all()
    form.group_id.choices = [(g.id, f"Kelompok {g.code}") for g in groups]


@admin_bp.get("/sessions")
@admin_required
def sessions_index():
    station_id = request.args.get("station_id", type=int)
    if not station_id and g.active_station:
        station_id = g.active_station.id

    stmt = db.select(CompetitionSession).order_by(CompetitionSession.created_at.desc())
    if station_id:
        stmt = stmt.where(CompetitionSession.station_id == station_id)
    sessions = db.session.scalars(stmt).all()

    session_data = []
    for s in sessions:
        eff_status = get_effective_status(s)
        rem = get_remaining_seconds(s)
        session_data.append({
            "session": s,
            "effective_status": eff_status,
            "remaining_seconds": rem,
        })

    action_form = SessionActionForm()
    return render_template(
        "admin/sessions/index.html",
        sessions=session_data,
        action_form=action_form,
        selected_station_id=station_id,
    )


@admin_bp.route("/sessions/create", methods=["GET", "POST"])
@admin_required
def sessions_create():
    form = SessionForm()
    _populate_session_form_choices(form)

    if request.method == "GET" and g.active_station:
        form.station_id.data = g.active_station.id

    if form.validate_on_submit():
        try:
            new_session = create_session(
                station_id=form.station_id.data,
                group_id=form.group_id.data,
                question_set_id=form.question_set_id.data or None,
                duration_minutes=form.duration_minutes.data,
            )
            flash(f"Sesi #{new_session.id} berhasil dibuat dengan status WAITING.", "success")
            return redirect(url_for("admin.sessions_detail", session_id=new_session.id))
        except ValueError as e:
            flash(str(e), "error")

    return render_template("admin/sessions/form.html", form=form, is_edit=False)


@admin_bp.get("/sessions/<int:session_id>")
@admin_required
def sessions_detail(session_id: int):
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "error")
        return redirect(url_for("admin.sessions_index"))

    effective_status = get_effective_status(session_obj)
    remaining_seconds = get_remaining_seconds(session_obj)
    action_form = SessionActionForm()
    monitoring = get_session_monitoring_data(session_obj)

    return render_template(
        "admin/sessions/detail.html",
        session=session_obj,
        effective_status=effective_status,
        remaining_seconds=remaining_seconds,
        action_form=action_form,
        monitoring=monitoring,
    )


@admin_bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
@admin_required
def sessions_edit(session_id: int):
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "error")
        return redirect(url_for("admin.sessions_index"))

    if session_obj.status != SessionStatus.WAITING:
        flash(f"Hanya sesi WAITING yang dapat diedit (status saat ini: {session_obj.status.value}).", "error")
        return redirect(url_for("admin.sessions_detail", session_id=session_obj.id))

    form = SessionForm()
    _populate_session_form_choices(form)

    # Ensure current question set choice is available if not in READY (e.g. if preserved)
    if session_obj.question_set:
        current_choice = (
            session_obj.question_set_id,
            f"{session_obj.station.name} — Set {session_obj.question_set.code} ({session_obj.question_set.name})",
        )
        if current_choice not in form.question_set_id.choices:
            form.question_set_id.choices.append(current_choice)

    if form.validate_on_submit():
        try:
            update_session(
                session_obj=session_obj,
                station_id=form.station_id.data,
                group_id=form.group_id.data,
                question_set_id=form.question_set_id.data or None,
                duration_minutes=form.duration_minutes.data,
            )
            flash("Data sesi berhasil diperbarui.", "success")
            return redirect(url_for("admin.sessions_detail", session_id=session_obj.id))
        except ValueError as e:
            flash(str(e), "error")
    elif request.method == "GET":
        form.station_id.data = session_obj.station_id
        form.group_id.data = session_obj.group_id
        form.question_set_id.data = session_obj.question_set_id or 0
        form.duration_minutes.data = int(session_obj.duration_seconds // 60)

    return render_template("admin/sessions/form.html", form=form, is_edit=True, session=session_obj)


@admin_bp.post("/sessions/<int:session_id>/start")
@admin_required
def sessions_start(session_id: int):
    action_form = SessionActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.sessions_detail", session_id=session_id))

    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "error")
        return redirect(url_for("admin.sessions_index"))

    success, msg = start_session(session_obj)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "warning" if "sudah berjalan" in msg.lower() else "error")

    return redirect(url_for("admin.sessions_detail", session_id=session_obj.id))


@admin_bp.post("/sessions/<int:session_id>/finish")
@admin_required
def sessions_finish(session_id: int):
    action_form = SessionActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.sessions_detail", session_id=session_id))

    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "error")
        return redirect(url_for("admin.sessions_index"))

    success, msg = finish_session(session_obj)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")

    return redirect(url_for("admin.sessions_detail", session_id=session_obj.id))


@admin_bp.post("/sessions/<int:session_id>/cancel")
@admin_required
def sessions_cancel(session_id: int):
    action_form = SessionActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.sessions_detail", session_id=session_id))

    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "error")
        return redirect(url_for("admin.sessions_index"))

    success, msg = cancel_session(session_obj)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "error")

    return redirect(url_for("admin.sessions_index"))


@admin_bp.post("/sessions/<int:session_id>/delete")
@admin_required
def sessions_delete(session_id: int):
    action_form = SessionActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.sessions_index"))

    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "error")
        return redirect(url_for("admin.sessions_index"))

    success, msg = delete_session(session_obj)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")

    return redirect(url_for("admin.sessions_index"))


@admin_bp.post("/sessions/clear-history")
@admin_required
def sessions_clear_history():
    action_form = SessionActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.sessions_index"))

    count, msg = clear_session_history(only_finished=True)
    if count > 0:
        flash(msg, "success")
    else:
        flash(msg, "info")

    return redirect(url_for("admin.sessions_index"))



# ==============================================================================
# HASIL LOMBA & AUDIT SUBMISSION (LANGKAH 8)
# ==============================================================================

@admin_bp.get("/results")
@admin_required
def results_index():
    station_id = request.args.get("station_id", type=int)
    if not station_id and g.active_station:
        station_id = g.active_station.id
    group_id = request.args.get("group_id", type=int)
    session_id = request.args.get("session_id", type=int)
    status = request.args.get("status", type=str)
    search_query = request.args.get("q", type=str)

    results = get_filtered_results(
        station_id=station_id,
        group_id=group_id,
        session_id=session_id,
        status=status,
        search_query=search_query,
    )

    stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.name.asc())
    ).all()
    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()
    sessions = db.session.scalars(
        db.select(CompetitionSession).order_by(CompetitionSession.id.desc())
    ).all()

    return render_template(
        "admin/results/index.html",
        results=results,
        stations=stations,
        groups=groups,
        sessions=sessions,
        selected_station_id=station_id,
        selected_group_id=group_id,
        selected_session_id=session_id,
        selected_status=status,
        search_query=search_query or "",
    )


@admin_bp.get("/results/<int:submission_id>")
@admin_required
def results_detail(submission_id: int):
    submission = db.session.get(Submission, submission_id)
    if not submission:
        flash("Data hasil penilaian (submission) tidak ditemukan.", "error")
        return redirect(url_for("admin.results_index"))

    session_obj = submission.session
    station = session_obj.station
    group = session_obj.group
    team = submission.team
    score = submission.score

    from services.quiz_service import get_session_questions
    questions = get_session_questions(session_obj)

    answers_map = {ans.question_id: ans for ans in submission.answers}

    audit_items = []
    for q in questions:
        ans = answers_map.get(q.id)
        sel_ans = ans.selected_answer if ans else None
        is_corr = ans.is_correct if ans else False
        pts = ans.points_awarded if ans else 0.0

        audit_items.append({
            "order_number": q.order_number,
            "question_id": q.id,
            "text": q.text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_answer": q.correct_answer,
            "selected_answer": sel_ans,
            "is_correct": is_corr,
            "weight": q.weight,
            "points_awarded": pts,
        })

    return render_template(
        "admin/results/detail.html",
        submission=submission,
        session=session_obj,
        station=station,
        group=group,
        team=team,
        score=score,
        audit_items=audit_items,
    )


@admin_bp.get("/results/export.csv")
@admin_required
def results_export_csv():
    station_id = request.args.get("station_id", type=int)
    group_id = request.args.get("group_id", type=int)
    session_id = request.args.get("session_id", type=int)
    status = request.args.get("status", type=str)
    search_query = request.args.get("q", type=str)

    results = get_filtered_results(
        station_id=station_id,
        group_id=group_id,
        session_id=session_id,
        status=status,
        search_query=search_query,
    )

    st_name = None
    if station_id:
        st_obj = db.session.get(Station, station_id)
        if st_obj:
            st_name = st_obj.name

    grp_code = None
    if group_id:
        grp_obj = db.session.get(Group, group_id)
        if grp_obj:
            grp_code = grp_obj.code

    csv_content, filename = generate_results_csv(results, station_name=st_name, group_code=grp_code)

    resp = Response(csv_content, mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ==============================================================================
# MANAJEMEN PAKET SOAL / STUDI KASUS (FITUR 1 & 2)
# ==============================================================================

@admin_bp.get("/packages")
@admin_required
def packages_index():
    """Daftar paket studi kasus hardware (khusus Pos Hardware)."""
    # Hanya Pos Hardware yang memiliki paket tantangan
    if g.active_station and g.active_station.name.lower() != "hardware":
        flash(f"Paket tantangan hanya digunakan untuk Pos Hardware. Pos {g.active_station.name} dikelola melalui Bank Soal.", "info")
        return redirect(url_for("admin.questions_index", station_id=g.active_station.id))

    status_filter = request.args.get("status", type=str)

    all_stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())
    ).all()

    hw_st = next((s for s in all_stations if s.name.lower() == "hardware"), None)
    selected_station = g.active_station or hw_st
    station_id = selected_station.id if selected_station else None

    packages = get_packages_by_station(station_id=station_id, status=status_filter)

    # Ambil info pemetaan kelompok untuk pos ini
    group_mappings = get_group_mappings_for_station(station_id) if station_id else {}

    package_data = []
    for p in packages:
        used = is_package_used(p.id)
        editable, lock_reason = is_package_editable(p)
        assigned_grps = [grp_code for grp_code, m in group_mappings.items() if m and m.package_id == p.id]
        package_data.append({
            "package": p,
            "is_used": used,
            "editable": editable,
            "lock_reason": lock_reason,
            "assigned_groups": assigned_grps,
        })

    action_form = PackageActionForm()

    return render_template(
        "admin/packages/index.html",
        stations=[hw_st] if hw_st else all_stations,
        selected_station=selected_station,
        packages=package_data,
        status_filter=status_filter or "all",
        action_form=action_form,
    )


@admin_bp.route("/packages/create", methods=["GET", "POST"])
@admin_required
def packages_create():
    """Form pembuatan paket tantangan studi kasus hardware baru (khusus Pos Hardware)."""
    if g.active_station and g.active_station.name.lower() != "hardware":
        flash("Paket tantangan hanya digunakan untuk Pos Hardware. Pos lain dikelola melalui Bank Soal.", "warning")
        return redirect(url_for("admin.questions_index", station_id=g.active_station.id))

    all_stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())
    ).all()

    hw_st = next((s for s in all_stations if s.name.lower() == "hardware"), None)
    selected_station = g.active_station or hw_st
    if not selected_station:
        abort(404)

    selected_station_id = selected_station.id

    form = HardwarePackageForm()
    form.station_id.choices = [(selected_station.id, f"{selected_station.name}")]

    if request.method == "GET":
        form.station_id.data = selected_station_id
        form.package_code.data = generate_next_package_code(selected_station_id)

    if form.validate_on_submit():
        st_id = selected_station.id
        pkg_code = form.package_code.data.strip()
        budget_val = form.max_budget.data if form.max_budget.data is not None else request.form.get("budget_max")
        budget_float = float(budget_val or 1500.0)

        rules_cfg = {
            "max_budget": budget_float,
            "budget_max": budget_float,
            "currency": form.currency.data.strip() or "USD",
            "region": form.region.data.strip() or "United States",
            "min_cpu_score": float(form.min_cpu_score.data or 1000.0),
            "min_gpu_score": float(form.min_gpu_score.data or 2000.0),
            "min_ram_gb": float(form.min_ram_gb.data or 16.0),
            "min_storage_gb": float(form.min_storage_gb.data or 512.0),
            "min_psu_watt": float(form.min_psu_watt.data or 550.0) if form.min_psu_watt.data else None,
            "required_components": form.required_components.data.strip() if form.required_components.data else "",
            "forbidden_components": form.forbidden_components.data.strip() if form.forbidden_components.data else "",
            "used_parts_allowed": bool(form.used_parts_allowed.data),
            "custom_price_allowed": bool(form.custom_price_allowed.data),
            "discount_allowed": bool(form.discount_allowed.data),
            "extra_notes": form.extra_notes.data.strip() if form.extra_notes.data else "",
        }

        scoring_cfg = {
            "weight_compatibility": float(form.weight_compatibility.data or 20.0),
            "weight_budget": float(form.weight_budget.data or 15.0),
            "weight_cpu_target": float(form.weight_cpu_target.data or 15.0),
            "weight_cpu": float(form.weight_cpu_target.data or 15.0),
            "weight_gpu_target": float(form.weight_gpu_target.data or 20.0),
            "weight_gpu": float(form.weight_gpu_target.data or 20.0),
            "weight_completeness": float(form.weight_completeness.data or 10.0),
            "weight_efficiency": float(form.weight_efficiency.data or 15.0),
            "weight_time_bonus": float(form.weight_time_bonus.data or 5.0),
        }

        try:
            status_enum = PackageStatus[form.status.data]
            new_pkg = create_package(
                station_id=st_id,
                package_code=pkg_code,
                title=form.title.data.strip(),
                description=form.description.data.strip(),
                instructions=form.instructions.data.strip(),
                challenge_type="hardware_build_challenge",
                external_tool_url=form.external_tool_url.data.strip(),
                rules_config=rules_cfg,
                scoring_config=scoring_cfg,
                duration_minutes=form.duration_minutes.data,
                status=status_enum,
            )
            flash(f"Paket Hardware '{new_pkg.package_code}' ({new_pkg.title}) berhasil dibuat.", "success")
            return redirect(url_for("admin.packages_index", station_id=st_id))
        except ValueError as e:
            flash(str(e), "error")

    return render_template(
        "admin/packages/form_hardware.html",
        form=form,
        stations=[hw_st] if hw_st else all_stations,
        selected_station_id=selected_station_id,
        is_edit=False,
    )


@admin_bp.route("/packages/<int:package_id>/edit", methods=["GET", "POST"])
@admin_required
def packages_edit(package_id: int):
    """Form pengeditan paket soal / studi kasus."""
    package = get_package_by_id(package_id)
    if not package:
        abort(404)

    # Validasi kepemilikan paket jika dalam konteks pos aktif
    if g.active_station and package.station_id != g.active_station.id:
        flash("Akses ditolak. Paket ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.packages_index", station_id=g.active_station.id))

    editable, reason = is_package_editable(package)
    if not editable:
        flash(reason, "error")
        return redirect(url_for("admin.packages_index", station_id=package.station_id))

    all_stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())
    ).all()

    # Jika paket bertipe hardware
    if package.challenge_type == "hardware_build_challenge":
        form = HardwarePackageForm(obj=package)
        form.station_id.choices = [(s.id, f"{s.name}") for s in all_stations]

        if request.method == "GET":
            form.station_id.data = package.station_id
            form.status.data = package.status.value
            rules = package.rules_config or {}
            scoring = package.scoring_config or {}

            form.max_budget.data = rules.get("max_budget", 1500.0)
            form.currency.data = rules.get("currency", "USD")
            form.region.data = rules.get("region", "United States")
            form.min_cpu_score.data = rules.get("min_cpu_score", 1000.0)
            form.min_gpu_score.data = rules.get("min_gpu_score", 2000.0)
            form.min_ram_gb.data = rules.get("min_ram_gb", 16.0)
            form.min_storage_gb.data = rules.get("min_storage_gb", 512.0)
            form.min_psu_watt.data = rules.get("min_psu_watt", 550.0)
            form.required_components.data = rules.get("required_components", "")
            form.forbidden_components.data = rules.get("forbidden_components", "")
            form.used_parts_allowed.data = rules.get("used_parts_allowed", False)
            form.custom_price_allowed.data = rules.get("custom_price_allowed", False)
            form.discount_allowed.data = rules.get("discount_allowed", True)
            form.extra_notes.data = rules.get("extra_notes", "")

            form.weight_compatibility.data = scoring.get("weight_compatibility", 20.0)
            form.weight_budget.data = scoring.get("weight_budget", 15.0)
            form.weight_cpu_target.data = scoring.get("weight_cpu_target", 15.0)
            form.weight_gpu_target.data = scoring.get("weight_gpu_target", 20.0)
            form.weight_completeness.data = scoring.get("weight_completeness", 10.0)
            form.weight_efficiency.data = scoring.get("weight_efficiency", 15.0)
            form.weight_time_bonus.data = scoring.get("weight_time_bonus", 5.0)

        if form.validate_on_submit():
            rules_cfg = {
                "max_budget": float(form.max_budget.data or 1500.0),
                "budget_max": float(form.max_budget.data or 1500.0),
                "currency": form.currency.data.strip() or "USD",
                "region": form.region.data.strip() or "United States",
                "min_cpu_score": float(form.min_cpu_score.data or 1000.0),
                "min_gpu_score": float(form.min_gpu_score.data or 2000.0),
                "min_ram_gb": float(form.min_ram_gb.data or 16.0),
                "min_storage_gb": float(form.min_storage_gb.data or 512.0),
                "min_psu_watt": float(form.min_psu_watt.data or 550.0) if form.min_psu_watt.data else None,
                "required_components": form.required_components.data.strip() if form.required_components.data else "",
                "forbidden_components": form.forbidden_components.data.strip() if form.forbidden_components.data else "",
                "used_parts_allowed": bool(form.used_parts_allowed.data),
                "custom_price_allowed": bool(form.custom_price_allowed.data),
                "discount_allowed": bool(form.discount_allowed.data),
                "extra_notes": form.extra_notes.data.strip() if form.extra_notes.data else "",
            }

            scoring_cfg = {
                "weight_compatibility": float(form.weight_compatibility.data or 20.0),
                "weight_budget": float(form.weight_budget.data or 15.0),
                "weight_cpu_target": float(form.weight_cpu_target.data or 15.0),
                "weight_cpu": float(form.weight_cpu_target.data or 15.0),
                "weight_gpu_target": float(form.weight_gpu_target.data or 20.0),
                "weight_gpu": float(form.weight_gpu_target.data or 20.0),
                "weight_completeness": float(form.weight_completeness.data or 10.0),
                "weight_efficiency": float(form.weight_efficiency.data or 15.0),
                "weight_time_bonus": float(form.weight_time_bonus.data or 5.0),
            }

            try:
                status_enum = PackageStatus[form.status.data]
                update_package(
                    package=package,
                    package_code=form.package_code.data.strip(),
                    title=form.title.data.strip(),
                    description=form.description.data.strip(),
                    instructions=form.instructions.data.strip(),
                    external_tool_url=form.external_tool_url.data.strip(),
                    rules_config=rules_cfg,
                    scoring_config=scoring_cfg,
                    duration_minutes=form.duration_minutes.data,
                    status=status_enum,
                )
                flash(f"Paket '{package.package_code}' berhasil diperbarui.", "success")
                return redirect(url_for("admin.packages_index", station_id=package.station_id))
            except ValueError as e:
                flash(str(e), "error")

        return render_template(
            "admin/packages/form_hardware.html",
            form=form,
            package=package,
            is_edit=True,
            stations=[package.station] if g.active_station else all_stations,
            selected_station_id=package.station_id,
        )

    else:
        flash("Hanya paket studi kasus Hardware yang dapat dikelola di modul ini.", "warning")
        return redirect(url_for("admin.packages_index"))


@admin_bp.post("/packages/<int:package_id>/duplicate")
@admin_required
def packages_duplicate(package_id: int):
    """Menduplikasi paket yang sudah ada menjadi draft salinan baru."""
    action_form = PackageActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.packages_index"))

    package = get_package_by_id(package_id)
    if not package:
        abort(404)

    if g.active_station and package.station_id != g.active_station.id:
        flash("Akses ditolak. Paket ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.packages_index"))

    try:
        dup = duplicate_package(package_id)
        flash(f"Paket berhasil diduplikasi menjadi '{dup.package_code}' dalam status DRAFT.", "success")
        return redirect(url_for("admin.packages_index", station_id=dup.station_id))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.packages_index"))


@admin_bp.get("/packages/<int:package_id>/preview")
@admin_required
def packages_preview(package_id: int):
    """Melihat pratinjau tampilan pengerjaan paket studi kasus oleh peserta."""
    package = get_package_by_id(package_id)
    if not package:
        abort(404)

    if g.active_station and package.station_id != g.active_station.id:
        flash("Akses ditolak. Paket ini bukan milik pos yang sedang Anda kelola.", "error")
        return redirect(url_for("admin.packages_index"))

    # Untuk paket kuis non-hardware yang terhubung ke QuestionSet, arahkan ke preview soal kuis
    if package.challenge_type != "hardware_build_challenge" and package.question_set_id:
        return redirect(url_for("admin.question_set_preview", set_id=package.question_set_id))

    return render_template("admin/packages/preview.html", package=package)


@admin_bp.post("/packages/<int:package_id>/status")
@admin_required
def packages_status(package_id: int):
    """Mengubah status paket (ACTIVE, LOCKED, ARCHIVED, DRAFT)."""
    action_form = PackageActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.packages_index"))

    package = get_package_by_id(package_id)
    if not package:
        abort(404)

    if g.active_station and package.station_id != g.active_station.id:
        flash("Akses ditolak. Tindakan ini hanya dapat dilakukan di dalam pos yang bersangkutan.", "error")
        return redirect(url_for("admin.packages_index"))

    new_status_str = request.form.get("status", "").strip().upper()
    try:
        new_status = PackageStatus[new_status_str]
        success, msg = set_package_status(package_id, new_status)
        if success:
            # Jika paket kuis, sinkronkan status QuestionSet
            if package.question_set_id:
                qs = db.session.get(QuestionSet, package.question_set_id)
                if qs:
                    if new_status == PackageStatus.ACTIVE:
                        qs.status = QuestionSetStatus.READY
                    elif new_status == PackageStatus.DRAFT:
                        qs.status = QuestionSetStatus.DRAFT
                db.session.commit()
            flash(msg, "success")
        else:
            flash(msg, "error")
    except KeyError:
        flash("Status paket tidak valid.", "error")

    st_id = package.station_id if package else None
    return redirect(url_for("admin.packages_index", station_id=st_id))


@admin_bp.post("/packages/<int:package_id>/delete")
@admin_required
def packages_delete(package_id: int):
    """Menghapus paket jika belum terpakai, atau mengarsipkan jika sudah ada riwayat."""
    action_form = PackageActionForm()
    if not action_form.validate_on_submit():
        flash("Token CSRF tidak valid.", "error")
        return redirect(url_for("admin.packages_index"))

    package = get_package_by_id(package_id)
    if not package:
        abort(404)

    if g.active_station and package.station_id != g.active_station.id:
        flash("Akses ditolak. Tindakan ini hanya dapat dilakukan di dalam pos yang bersangkutan.", "error")
        return redirect(url_for("admin.packages_index"))

    st_id = package.station_id

    success, msg = delete_or_archive_package(package_id)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "error")

    return redirect(url_for("admin.packages_index", station_id=st_id))


@admin_bp.route("/packages/mapping", methods=["GET", "POST"])
@admin_required
def packages_mapping():
    """Halaman pengelolaan pemetaan paket soal kepada Kelompok A, B, C, D."""
    all_stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.id.asc())
    ).all()

    if g.active_station and g.active_station.name.lower() != "hardware":
        flash(f"Pemetaan paket hanya digunakan untuk Pos Hardware. Pos {g.active_station.name} dikelola melalui Bank Soal.", "info")
        return redirect(url_for("admin.questions_index", station_id=g.active_station.id))

    hw_st = next((s for s in all_stations if s.name.lower() == "hardware"), None)
    selected_station = g.active_station or hw_st
    station_id = selected_station.id if selected_station else None

    # Ambil seluruh paket aktif pada pos ini
    active_packages = db.session.scalars(
        db.select(ChallengePackage).where(
            ChallengePackage.station_id == station_id,
            ChallengePackage.status.in_((PackageStatus.ACTIVE, PackageStatus.LOCKED)),
        ).order_by(ChallengePackage.package_code.asc())
    ).all()

    pkg_choices = [(p.id, f"{p.package_code} — {p.title}") for p in active_packages]

    form = PackageMappingForm()
    form.same_package_id.choices = [(-1, "-- Pilih Paket Bersama --")] + pkg_choices
    form.package_group_a.choices = [(-1, "-- Pilih Paket Kelompok A --")] + pkg_choices
    form.package_group_b.choices = [(-1, "-- Pilih Paket Kelompok B --")] + pkg_choices
    form.package_group_c.choices = [(-1, "-- Pilih Paket Kelompok C --")] + pkg_choices
    form.package_group_d.choices = [(-1, "-- Pilih Paket Kelompok D --")] + pkg_choices

    current_mappings = get_group_mappings_for_station(station_id)

    if request.method == "GET":
        map_a = current_mappings.get("A")
        map_b = current_mappings.get("B")
        map_c = current_mappings.get("C")
        map_d = current_mappings.get("D")

        if map_a and map_b and map_c and map_d and (map_a.package_id == map_b.package_id == map_c.package_id == map_d.package_id):
            form.strategy.data = "SAME_FOR_ALL"
            form.same_package_id.data = map_a.package_id
        else:
            form.strategy.data = "BY_GROUP"

        if map_a:
            form.package_group_a.data = map_a.package_id
        if map_b:
            form.package_group_b.data = map_b.package_id
        if map_c:
            form.package_group_c.data = map_c.package_id
        if map_d:
            form.package_group_d.data = map_d.package_id

    if form.validate_on_submit():
        strat = form.strategy.data
        if strat == "SAME_FOR_ALL":
            pkg_id = form.same_package_id.data
            if not pkg_id or pkg_id == -1:
                flash("Silakan pilih paket bersama untuk strategi SAME_FOR_ALL.", "error")
            else:
                ok, msg = apply_same_for_all_mapping(station_id, pkg_id)
                if ok:
                    flash(msg, "success")
                    return redirect(url_for("admin.packages_mapping", station_id=station_id))
                else:
                    flash(msg, "error")
        elif strat == "BY_GROUP":
            grp_dict = {
                "A": form.package_group_a.data if form.package_group_a.data != -1 else None,
                "B": form.package_group_b.data if form.package_group_b.data != -1 else None,
                "C": form.package_group_c.data if form.package_group_c.data != -1 else None,
                "D": form.package_group_d.data if form.package_group_d.data != -1 else None,
            }
            if not any(grp_dict.values()):
                flash("Pilih minimal satu paket untuk kelompok.", "error")
            else:
                ok, msg = apply_by_group_mapping(station_id, grp_dict)
                if ok:
                    flash(msg, "success")
                    return redirect(url_for("admin.packages_mapping", station_id=station_id))
                else:
                    flash(msg, "error")

    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()

    return render_template(
        "admin/packages/mapping.html",
        form=form,
        stations=all_stations,
        selected_station=selected_station,
        active_packages=active_packages,
        current_mappings=current_mappings,
        groups=groups,
    )


# ==============================================================================
# VERIFIKASI & REVIEW SUBMISSION POS HARDWARE (FITUR 5)
# ==============================================================================

@admin_bp.get("/hardware/submissions")
@admin_required
def hardware_submissions_index():
    """Daftar submission Pos Hardware dengan filter status dan informasi tim."""
    status_filter = request.args.get("status", "all").strip()

    stmt = (
        db.select(HardwareSubmission)
        .join(Submission, HardwareSubmission.submission_id == Submission.id)
        .join(Team, Submission.team_id == Team.id)
        .join(CompetitionSession, Submission.session_id == CompetitionSession.id)
        .join(Group, CompetitionSession.group_id == Group.id)
        .join(Station, CompetitionSession.station_id == Station.id)
        .order_by(Submission.submitted_at.desc(), HardwareSubmission.id.desc())
    )

    if status_filter and status_filter != "all":
        stmt = stmt.where(HardwareSubmission.verification_status == status_filter.upper())

    submissions = db.session.scalars(stmt).all()

    return render_template(
        "admin/hardware/submissions.html",
        submissions=submissions,
        status_filter=status_filter,
    )


@admin_bp.route("/hardware/submissions/<int:hw_id>/review", methods=["GET", "POST"])
@admin_required
def hardware_submission_review(hw_id: int):
    """Detail submission Pos Hardware, verifikasi kesesuaian BuildCores, koreksi, dan scoring."""
    hw_sub = db.session.get(HardwareSubmission, hw_id)
    if not hw_sub:
        abort(404)

    submission = hw_sub.submission
    session_obj = submission.session
    station = session_obj.station
    group = session_obj.group
    team = submission.team
    package = submission.package or session_obj.package
    rules = (submission.package_snapshot or {}).get("rules_config") or (package.rules_config if package else {})
    scoring = (submission.package_snapshot or {}).get("scoring_config") or (package.scoring_config if package else {})

    form = HardwareReviewForm()

    if request.method == "GET":
        form.is_compatible.data = "1" if (hw_sub.is_compatible is None or hw_sub.is_compatible) else "0"
        form.corrected_price.data = hw_sub.total_price
        form.corrected_cpu_score.data = hw_sub.cpu_score
        form.corrected_gpu_score.data = hw_sub.gpu_score
        form.reviewer_notes.data = hw_sub.reviewer_notes or ""

    if form.validate_on_submit():
        action = request.form.get("action", "VERIFY").strip().upper()
        reason = form.reason.data.strip() if form.reason.data else f"Verifikasi submission via action {action}"

        corrected = {
            "is_compatible": (form.is_compatible.data == "1"),
            "total_price": form.corrected_price.data,
            "cpu_score": form.corrected_cpu_score.data,
            "gpu_score": form.corrected_gpu_score.data,
            "reviewer_notes": form.reviewer_notes.data,
        }

        success, msg = review_hardware_submission(
            hardware_submission_id=hw_sub.id,
            admin_id=g.current_admin.id,
            action=action,
            corrected_data=corrected,
            reason=reason,
        )

        if success:
            flash(msg, "success")
            return redirect(url_for("admin.hardware_submissions_index"))
        else:
            flash(msg, "error")

    audits = hw_sub.audits

    return render_template(
        "admin/hardware/review.html",
        hw_sub=hw_sub,
        submission=submission,
        session=session_obj,
        station=station,
        group=group,
        team=team,
        package=package,
        rules=rules,
        scoring=scoring,
        form=form,
        audits=audits,
    )


# ==============================================================================
# MODUL POS NETWORKING (FASILITATOR LOBBY, MONITOR, VERIFIKASI & STAMP)
# ==============================================================================

@admin_bp.route("/networking/lobby", methods=["GET"])
@admin_required
def networking_lobby():
    """Halaman Lobby Fasilitator Pos Networking untuk pemilihan rotasi, kelompok, dan set soal."""
    net_station = db.session.scalar(db.select(Station).where(Station.name == "Networking"))
    if not net_station:
        flash("Pos Networking tidak ditemukan dalam basis data.", "danger")
        return redirect(url_for("admin.dashboard"))

    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()
    question_sets = db.session.scalars(
        db.select(QuestionSet).where(QuestionSet.station_id == net_station.id).order_by(QuestionSet.code.asc())
    ).all()

    # Param rotasi & kelompok dari query string
    selected_rotation = request.args.get("rotation", default=1, type=int)
    group_id_param = request.args.get("group_id", type=int)
    set_id_param = request.args.get("set_id", type=int)

    selected_group = next((g for g in groups if g.id == group_id_param), groups[0] if groups else None)
    if not selected_group:
        flash("Kelompok peserta belum tersedia.", "warning")
        return redirect(url_for("admin.dashboard"))

    # Pemetaan otomatis: Kelompok A -> Set A, dsb
    selected_set = None
    if set_id_param:
        selected_set = next((qs for qs in question_sets if qs.id == set_id_param), None)
    if not selected_set and selected_group:
        selected_set = next((qs for qs in question_sets if qs.code.upper() == selected_group.code.upper()), None)
    if not selected_set and question_sets:
        selected_set = question_sets[0]

    # Cari sesi aktif untuk rotasi dan kelompok ini
    active_session = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.station_id == net_station.id,
            CompetitionSession.group_id == selected_group.id,
            CompetitionSession.status.in_((SessionStatus.WAITING, SessionStatus.RUNNING)),
        ).order_by(CompetitionSession.id.desc())
    )

    # Ambil tim dalam kelompok
    teams = db.session.scalars(
        db.select(Team).where(Team.group_id == selected_group.id, Team.is_active.is_(True)).order_by(Team.team_code.asc())
    ).all()

    teams_status = []
    for t in teams:
        sub = None
        net_sub = None
        if active_session:
            sub = db.session.scalar(
                db.select(Submission).where(
                    Submission.session_id == active_session.id,
                    Submission.team_id == t.id,
                )
            )
            if sub:
                net_sub = sub.networking_submission

        st_label = "BELUM_MASUK"
        current_st = 1
        has_stamp = False
        if net_sub:
            st_label = net_sub.verification_status
            current_st = net_sub.current_stage
            has_stamp = net_sub.has_stamp
        elif sub:
            st_label = "LOBBY"

        teams_status.append({
            "team": t,
            "has_submission": sub is not None,
            "net_status": st_label,
            "current_stage": current_st,
            "has_stamp": has_stamp,
        })

    return render_template(
        "admin/networking/lobby.html",
        station=net_station,
        groups=groups,
        question_sets=question_sets,
        selected_rotation=selected_rotation,
        selected_group=selected_group,
        selected_set=selected_set,
        active_session=active_session,
        teams_status=teams_status,
    )


@admin_bp.post("/networking/open-lobby")
@admin_required
def networking_open_lobby():
    """Membuka atau menyiapkan sesi lobby Pos Networking untuk kelompok tertentu."""
    net_station = db.session.scalar(db.select(Station).where(Station.name == "Networking"))
    if not net_station:
        flash("Pos Networking tidak ditemukan.", "danger")
        return redirect(url_for("admin.dashboard"))

    group_id = request.form.get("group_id", type=int)
    rotation = request.form.get("rotation", default=1, type=int)
    set_id = request.form.get("set_id", type=int)

    group = db.session.get(Group, group_id)
    if not group:
        flash("Kelompok tidak valid.", "danger")
        return redirect(url_for("admin.networking_lobby"))

    # Cek apakah sesi aktif sudah ada
    existing = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.station_id == net_station.id,
            CompetitionSession.group_id == group.id,
            CompetitionSession.status.in_((SessionStatus.WAITING, SessionStatus.RUNNING)),
        )
    )
    if existing:
        flash(f"Lobby sesi untuk Kelompok {group.code} sudah aktif (Sesi #{existing.id}).", "info")
        return redirect(url_for("admin.networking_lobby", group_id=group.id, rotation=rotation))

    new_session = CompetitionSession(
        station_id=net_station.id,
        group_id=group.id,
        question_set_id=set_id,
        rotation_number=rotation,
        status=SessionStatus.WAITING,
        duration_seconds=1800,  # 30 menit default
    )
    db.session.add(new_session)
    db.session.commit()
    flash(f"Lobby sesi untuk Kelompok {group.code} berhasil disiapkan! Silakan mulai sesi saat tim telah siap.", "success")
    return redirect(url_for("admin.networking_lobby", group_id=group.id, rotation=rotation))


@admin_bp.get("/networking/monitor/<int:session_id>")
@admin_required
def networking_monitor(session_id: int):
    """Layar Live Monitoring sesi Pos Networking tanpa membocorkan kunci jawaban."""
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj or session_obj.station.name.lower() != "networking":
        flash("Sesi Pos Networking tidak ditemukan.", "danger")
        return redirect(url_for("admin.networking_lobby"))

    from services.networking_service import get_stage_questions, get_stage_timer_info

    teams = db.session.scalars(
        db.select(Team).where(Team.group_id == session_obj.group_id, Team.is_active.is_(True)).order_by(Team.team_code.asc())
    ).all()

    subs = db.session.scalars(
        db.select(Submission).where(Submission.session_id == session_id)
    ).all()
    subs_map = {s.team_id: s for s in subs}

    team_monitors = []
    for t in teams:
        sub = subs_map.get(t.id)
        net_sub = sub.networking_submission if sub else None

        current_st = net_sub.current_stage if net_sub else 1
        timer_info = get_stage_timer_info(net_sub, current_st) if net_sub else {"remaining_seconds": 0, "is_locked": True}

        # Hitung jumlah soal tahap
        stage_questions = get_stage_questions(session_obj, current_st if current_st <= 3 else 3)
        q_ids = {q.id for q in stage_questions}

        answered_count = 0
        if sub:
            ans = db.session.scalars(
                db.select(Answer).where(Answer.submission_id == sub.id, Answer.question_id.in_(q_ids))
            ).all()
            answered_count = sum(1 for a in ans if (a.selected_answer or a.text_answer))

        total_q = len(stage_questions) or 10
        prog_pct = min(100, int((answered_count / total_q) * 100))

        team_monitors.append({
            "team": t,
            "sub": sub,
            "net_sub": net_sub,
            "timer_info": timer_info,
            "answered_count": answered_count,
            "stage_total_questions": total_q,
            "progress_percent": prog_pct,
        })

    pending_review_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(Answer)
        .join(Submission, Answer.submission_id == Submission.id)
        .where(Submission.session_id == session_id, Answer.review_status == "NEEDS_REVIEW")
    ) or 0

    return render_template(
        "admin/networking/monitor.html",
        session_obj=session_obj,
        team_monitors=team_monitors,
        pending_review_count=pending_review_count,
    )


@admin_bp.get("/networking/verify/<int:session_id>")
@admin_required
def networking_verify(session_id: int):
    """Antrean verifikasi jawaban isian singkat dan kelayakan Stamp Pos Networking."""
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj or session_obj.station.name.lower() != "networking":
        flash("Sesi Pos Networking tidak ditemukan.", "danger")
        return redirect(url_for("admin.networking_lobby"))

    from services.networking_service import get_facilitator_review_queue

    review_queue = get_facilitator_review_queue(session_id)

    # Rekapitulasi nilai & Stamp tim
    teams = db.session.scalars(
        db.select(Team).where(Team.group_id == session_obj.group_id, Team.is_active.is_(True)).order_by(Team.team_code.asc())
    ).all()

    subs = db.session.scalars(
        db.select(Submission).where(Submission.session_id == session_id)
    ).all()
    subs_map = {s.team_id: s for s in subs}

    team_summaries = []
    for t in teams:
        sub = subs_map.get(t.id)
        net_sub = sub.networking_submission if sub else None
        team_summaries.append({
            "team": t,
            "sub": sub,
            "net_sub": net_sub,
        })

    return render_template(
        "admin/networking/verify.html",
        session_obj=session_obj,
        review_queue=review_queue,
        team_summaries=team_summaries,
    )


@admin_bp.post("/networking/review-answer")
@admin_required
def networking_review_answer():
    """Fasilitator memutuskan penerimaan jawaban isian singkat (ACCEPT / REJECT)."""
    answer_id = request.form.get("answer_id", type=int)
    session_id = request.form.get("session_id", type=int)
    action = request.form.get("action", default="REJECT")
    notes = request.form.get("notes", default="")

    from services.networking_service import review_answer_by_facilitator

    ok, msg = review_answer_by_facilitator(answer_id, g.current_admin.id, action, notes)
    if ok:
        flash("Keputusan verifikasi berhasil disimpan.", "success")
    else:
        flash(msg or "Gagal memproses verifikasi jawaban.", "danger")

    return redirect(url_for("admin.networking_verify", session_id=session_id))


@admin_bp.post("/networking/finalize-session/<int:session_id>")
@admin_required
def networking_finalize_session(session_id: int):
    """Finalisasi nilai seluruh tim pada sesi Pos Networking dan pengiriman ke leaderboard."""
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        flash("Sesi tidak ditemukan.", "danger")
        return redirect(url_for("admin.networking_lobby"))

    from services.networking_service import finalize_networking_submission

    subs = db.session.scalars(
        db.select(Submission).where(Submission.session_id == session_id)
    ).all()

    finalized_count = 0
    for sub in subs:
        if sub.networking_submission:
            ok, msg, _ = finalize_networking_submission(
                sub.networking_submission.id,
                g.current_admin.id,
                "Finalisasi massal sesi pos networking oleh fasilitator",
            )
            if ok:
                finalized_count += 1

    session_obj.status = SessionStatus.FINISHED
    db.session.commit()

    flash(f"Berhasil memfinalisasi skor dan Stamp untuk {finalized_count} tim! Hasil telah dipublikasikan ke Leaderboard.", "success")
    return redirect(url_for("admin.networking_verify", session_id=session_id))


@admin_bp.post("/networking/control")
@admin_required
def networking_control():
    """Endpoint penanganan kontrol fasilitator (START_SESSION, ADD_TIME, FORCE_SUBMIT, ALLOW_RECONNECT)."""
    session_id = request.form.get("session_id", type=int)
    action = request.form.get("action", "").strip()
    reason = request.form.get("reason", "").strip()
    team_id = request.form.get("team_id", type=int)
    extra_seconds = request.form.get("extra_seconds", default=0, type=int)
    stage_num = request.form.get("stage_num", default=1, type=int)

    from services.networking_service import facilitator_control_action

    ok, msg = facilitator_control_action(
        session_id=session_id,
        action=action,
        admin_id=g.current_admin.id,
        reason=reason,
        team_id=team_id,
        extra_seconds=extra_seconds,
        stage_num=stage_num,
    )

    if ok:
        flash(msg or "Tindakan kontrol berhasil dijalankan.", "success")
    else:
        flash(msg or "Gagal menjalankan aksi kontrol.", "danger")

    if action == "START_SESSION":
        return redirect(url_for("admin.networking_monitor", session_id=session_id))
    return redirect(url_for("admin.networking_monitor", session_id=session_id))


# ==============================================================================
# PLACEHOLDERS FALLBACK
# ==============================================================================

PLACEHOLDERS = {}


@admin_bp.get("/<string:page>")
@admin_required
def placeholder(page):
    content = PLACEHOLDERS.get(page)
    if content is None:
        abort(404)
    return render_template("admin/placeholder.html", title=content[0], message=content[1])
