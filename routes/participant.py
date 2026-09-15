from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from forms.participant import (
    EmptyForm,
    ParticipantAccessForm,
    ParticipantTeamForm,
    SelectionForm,
)
from models import Group, Station, StationMode, Team, db
from utils.participant_session import (
    KEY_AUTHORIZED,
    KEY_CONFIRMED,
    KEY_GROUP_ID,
    KEY_RULES_ACCEPTED,
    KEY_STATION_ID,
    KEY_TEAM_ID,
    clear_downstream_after_group,
    clear_downstream_after_station,
    clear_downstream_after_team,
    clear_participant_session,
    get_next_required_participant_endpoint,
    get_participant_context,
    require_participant_stage,
)
from services.session_service import (
    find_participant_session,
    get_effective_status,
    get_remaining_seconds,
)

participant_bp = Blueprint("participant", __name__, url_prefix="/participant")


# Pos rule descriptions based on station mode & station name
STATION_MODE_RULES = {
    StationMode.MEMBER_ROTATION: [
        "Mode POS: ROTASI ANGGOTA (MEMBER ROTATION).",
        "Setiap anggota tim wajib bergantian mengerjakan soal sesuai urutan giliran.",
        "Anggota yang sedang tidak berada di layar dilarang membocorkan jawaban atau menggantikan pengerjaan.",
        "Komunikasi taktis hanya diperbolehkan saat jeda rotasi yang ditentukan oleh panitia pos.",
    ],
    StationMode.NORMAL: [
        "Mode POS: KERJA SAMA TIM (NORMAL COLLABORATION).",
        "Seluruh anggota tim diperbolehkan berdiskusi secara internal dalam pos.",
        "Satu perangkat digunakan bersama untuk memasukkan jawaban tim.",
    ],
    StationMode.BELUM_DIKETAHUI: [
        "Mode POS: BELUM DIKETAHUI.",
        "Format dan mekanisme pengerjaan untuk pos ini belum ditentukan.",
        "Silakan tunggu arahan dan instruksi lebih lanjut dari panitia lomba.",
    ],
}

COMMON_RULES = [
    "Dilarang membuka tab browser lain, search engine, atau aplikasi di luar sistem lomba.",
    "Dilarang bekerja sama atau berkomunikasi dengan kelompok/tim lain selama sesi berlangsung.",
    "Waktu pengerjaan dan status sesi dikendalikan terpusat oleh sistem dan panitia pos.",
    "Patuhi seluruh aba-aba dan instruksi panitia di pos ini.",
]


@participant_bp.get("/health")
def health():
    return {"area": "participant", "status": "ok"}


@participant_bp.route("/access", methods=["GET", "POST"])
def access():
    form = ParticipantAccessForm()

    # If already authorized, redirect directly to next required stage
    if session.get(KEY_AUTHORIZED):
        return redirect(url_for(get_next_required_participant_endpoint()))

    if form.validate_on_submit():
        entered_code = form.access_code.data.strip().upper()
        expected_code = current_app.config.get("PARTICIPANT_ACCESS_CODE", "QUEST2026").strip().upper()

        if entered_code == expected_code:
            session[KEY_AUTHORIZED] = True
            flash("Kode akses valid! Silakan pilih pos perlombaan Anda.", "success")
            return redirect(url_for("participant.station_select"))
        else:
            flash("Kode akses tidak valid. Silakan tanyakan kode akses kepada panitia.", "danger")

    return render_template("participant/access.html", form=form)


@participant_bp.route("/station", methods=["GET", "POST"])
@require_participant_stage("authorized")
def station_select():
    form = SelectionForm()
    station_priority = db.case(
        {"Software Engineering": 1, "Cyber Security": 2, "Hardware": 3, "Networking": 4},
        value=Station.name,
        else_=99,
    )
    active_stations = (
        Station.query.filter_by(is_active=True)
        .order_by(station_priority, Station.id.asc())
        .all()
    )

    if request.method == "POST":
        raw_items = [x for x in request.form.getlist("item_id") if x and str(x).strip()]
        if raw_items and not form.item_id.data:
            form.item_id.raw_data = [raw_items[-1]]
            form.item_id.data = raw_items[-1]

    if form.validate_on_submit():
        try:
            station_id = int(form.item_id.data)
        except (ValueError, TypeError):
            flash("Pilihan pos tidak valid.", "danger")
            return redirect(url_for("participant.station_select"))

        station = Station.query.filter_by(id=station_id, is_active=True).first()
        if not station:
            flash("Pos perlombaan yang dipilih tidak ditemukan atau sedang tidak aktif.", "danger")
            return redirect(url_for("participant.station_select"))

        # Save station and reset downstream selections
        if session.get(KEY_STATION_ID) != station.id:
            clear_downstream_after_station()
        session[KEY_STATION_ID] = station.id

        flash(f"Pos '{station.name}' berhasil dipilih.", "success")
        return redirect(url_for("participant.group_select"))

    ctx = get_participant_context()
    return render_template(
        "participant/station.html",
        stations=active_stations,
        selected_station_id=session.get(KEY_STATION_ID),
        form=form,
        ctx=ctx,
    )


@participant_bp.route("/group", methods=["GET", "POST"])
@require_participant_stage("station")
def group_select():
    form = SelectionForm()
    groups = Group.query.order_by(Group.code.asc()).all()

    if request.method == "POST":
        raw_items = [x for x in request.form.getlist("item_id") if x and str(x).strip()]
        if raw_items and not form.item_id.data:
            form.item_id.raw_data = [raw_items[-1]]
            form.item_id.data = raw_items[-1]

    if form.validate_on_submit():
        try:
            group_id = int(form.item_id.data)
        except (ValueError, TypeError):
            flash("Pilihan kelompok tidak valid.", "danger")
            return redirect(url_for("participant.group_select"))

        group = db.session.get(Group, group_id)
        if not group:
            flash("Kelompok yang dipilih tidak ditemukan.", "danger")
            return redirect(url_for("participant.group_select"))

        # Save group and reset downstream selections
        if session.get(KEY_GROUP_ID) != group.id:
            clear_downstream_after_group()
        session[KEY_GROUP_ID] = group.id

        flash(f"Kelompok '{group.code}' berhasil dipilih.", "success")
        return redirect(url_for("participant.team_select"))

    ctx = get_participant_context()
    return render_template(
        "participant/group.html",
        groups=groups,
        selected_group_id=session.get(KEY_GROUP_ID),
        form=form,
        ctx=ctx,
    )


def generate_unique_team_code(group_code: str) -> str:
    """Generate a clean, unique team code for a group, e.g. A01, A02..."""
    prefix = group_code.strip().upper()
    existing_codes = db.session.scalars(
        db.select(Team.team_code).where(Team.team_code.like(f"{prefix}%"))
    ).all()
    nums = []
    for code in existing_codes:
        suffix = code[len(prefix):].lstrip("-").strip()
        if suffix.isdigit():
            nums.append(int(suffix))
    next_num = max(nums) + 1 if nums else 1
    new_code = f"{prefix}{next_num:02d}"
    while db.session.scalar(db.select(Team).where(Team.team_code == new_code)):
        next_num += 1
        new_code = f"{prefix}{next_num:02d}"
    return new_code


@participant_bp.route("/team", methods=["GET", "POST"])
@require_participant_stage("group")
def team_select():
    form = ParticipantTeamForm()
    ctx = get_participant_context()
    selected_group = ctx["group"]

    active_teams = (
        Team.query.filter_by(group_id=selected_group.id, is_active=True)
        .order_by(Team.team_code.asc())
        .all()
    )

    if request.method == "GET" and ctx["team"]:
        form.team_name.data = ctx["team"].team_name
        form.school.data = ctx["team"].school
        form.item_id.data = str(ctx["team"].id)

    if request.method == "POST":
        raw_items = [x for x in request.form.getlist("item_id") if x and str(x).strip()]
        if raw_items and not form.item_id.data:
            form.item_id.raw_data = [raw_items[-1]]
            form.item_id.data = raw_items[-1]

        if form.validate_on_submit():
            team_name_val = (request.form.get("team_name") or "").strip()
            school_val = (request.form.get("school") or "").strip()
            item_id_val = (request.form.get("item_id") or "").strip()

            # Priority 1: Participant entered team name & school (metode isian)
            if team_name_val:
                if not school_val:
                    flash("Asal sekolah wajib diisi.", "danger")
                    return render_template(
                        "participant/team.html",
                        teams=active_teams,
                        selected_group=selected_group,
                        selected_team_id=session.get(KEY_TEAM_ID),
                        form=form,
                        ctx=ctx,
                    )

                if len(team_name_val) < 2 or len(team_name_val) > 120:
                    flash("Nama tim harus antara 2 hingga 120 karakter.", "danger")
                    return render_template(
                        "participant/team.html",
                        teams=active_teams,
                        selected_group=selected_group,
                        selected_team_id=session.get(KEY_TEAM_ID),
                        form=form,
                        ctx=ctx,
                    )

                if len(school_val) < 2 or len(school_val) > 160:
                    flash("Asal sekolah harus antara 2 hingga 160 karakter.", "danger")
                    return render_template(
                        "participant/team.html",
                        teams=active_teams,
                        selected_group=selected_group,
                        selected_team_id=session.get(KEY_TEAM_ID),
                        form=form,
                        ctx=ctx,
                    )

                # Check if team already exists with the same name in this group (case-insensitive)
                matched_team = db.session.scalar(
                    db.select(Team).where(
                        Team.group_id == selected_group.id,
                        db.func.lower(Team.team_name) == team_name_val.lower(),
                    )
                )

                if matched_team:
                    team = matched_team
                    if team.school != school_val or not team.is_active:
                        team.school = school_val
                        team.is_active = True
                        db.session.commit()
                else:
                    new_code = generate_unique_team_code(selected_group.code)
                    team = Team(
                        team_code=new_code,
                        team_name=team_name_val,
                        school=school_val,
                        group_id=selected_group.id,
                        is_active=True,
                    )
                    db.session.add(team)
                    db.session.commit()

                if session.get(KEY_TEAM_ID) != team.id:
                    clear_downstream_after_team()
                session[KEY_TEAM_ID] = team.id

                flash(f"Data tim '{team.team_name}' ({team.team_code}) berhasil disimpan.", "success")
                return redirect(url_for("participant.confirm"))

            # Priority 2: Selected from item_id (backward compatibility / quick pick / tests)
            elif item_id_val:
                try:
                    team_id = int(item_id_val)
                except (ValueError, TypeError):
                    flash("Pilihan tim tidak valid.", "danger")
                    return redirect(url_for("participant.team_select"))

                team = Team.query.filter_by(id=team_id, is_active=True).first()
                if not team or team.group_id != selected_group.id:
                    flash(
                        "Pilihan tim tidak valid, tidak aktif, atau tidak terdaftar di kelompok yang dipilih.",
                        "danger",
                    )
                    return redirect(url_for("participant.team_select"))

                if session.get(KEY_TEAM_ID) != team.id:
                    clear_downstream_after_team()
                session[KEY_TEAM_ID] = team.id

                flash(f"Tim '{team.team_name}' ({team.team_code}) berhasil dipilih.", "success")
                return redirect(url_for("participant.confirm"))

            else:
                flash("Silakan isi nama tim dan asal sekolah Anda.", "danger")

    return render_template(
        "participant/team.html",
        teams=active_teams,
        selected_group=selected_group,
        selected_team_id=session.get(KEY_TEAM_ID),
        form=form,
        ctx=ctx,
    )


@participant_bp.route("/confirm", methods=["GET", "POST"])
@require_participant_stage("team")
def confirm():
    form = EmptyForm()
    ctx = get_participant_context()

    if form.validate_on_submit():
        session[KEY_CONFIRMED] = True
        flash("Identitas tim berhasil dikonfirmasi!", "success")
        return redirect(url_for("participant.rules"))

    return render_template(
        "participant/confirm.html",
        station=ctx["station"],
        group=ctx["group"],
        team=ctx["team"],
        form=form,
        ctx=ctx,
    )


@participant_bp.route("/rules", methods=["GET", "POST"])
@require_participant_stage("confirmed")
def rules():
    form = EmptyForm()
    ctx = get_participant_context()
    station = ctx["station"]

    # Gather rules for station
    mode_rules = STATION_MODE_RULES.get(station.mode, ["Ikuti instruksi panitia pada pos ini."])
    all_rules = mode_rules + COMMON_RULES

    if form.validate_on_submit():
        session[KEY_RULES_ACCEPTED] = True
        flash("Aturan lomba telah diterima. Selamat datang di Ruang Tunggu!", "success")
        return redirect(url_for("participant.waiting"))

    return render_template(
        "participant/rules.html",
        station=station,
        group=ctx["group"],
        team=ctx["team"],
        rules=all_rules,
        form=form,
        ctx=ctx,
    )


@participant_bp.route("/waiting")
@require_participant_stage("rules_accepted")
def waiting():
    ctx = get_participant_context()
    team = ctx["team"]

    # Inactive team check
    if not team or not team.is_active:
        clear_downstream_after_group()
        flash(
            "Tim Anda sedang tidak aktif atau dinonaktifkan oleh panitia. Silakan hubungi panitia.",
            "danger",
        )
        return redirect(url_for("participant.team_select"))

    reset_form = EmptyForm()
    return render_template(
        "participant/waiting.html",
        station=ctx["station"],
        group=ctx["group"],
        team=team,
        reset_form=reset_form,
        ctx=ctx,
    )


@participant_bp.get("/quiz")
@require_participant_stage("rules_accepted")
def quiz():
    ctx = get_participant_context()
    team = ctx["team"]
    station = ctx["station"]
    group = ctx["group"]

    if not team or not team.is_active:
        clear_downstream_after_group()
        flash("Tim Anda sedang tidak aktif. Silakan hubungi panitia.", "danger")
        return redirect(url_for("participant.team_select"))

    session_obj = find_participant_session(station.id, group.id)
    if not session_obj:
        flash("Sesi perlombaan belum disiapkan oleh panitia. Silakan menunggu di ruang tunggu.", "info")
        return redirect(url_for("participant.waiting"))

    effective_status = get_effective_status(session_obj)

    if effective_status.value == "WAITING":
        flash("Sesi perlombaan belum dimulai oleh panitia. Harap tetap berada di ruang tunggu.", "info")
        return redirect(url_for("participant.waiting"))

    if effective_status.value == "CANCELLED":
        flash("Sesi perlombaan ini dibatalkan oleh panitia.", "warning")
        return redirect(url_for("participant.waiting"))

    from models import SubmissionStatus
    from services.quiz_service import (
        get_or_create_submission,
        get_session_questions,
        get_submission_answers_map,
        partition_questions_for_members,
    )
    from services.scoring_service import finalize_submission

    submission = get_or_create_submission(session_obj.id, team.id)

    # Jika submission sudah difinalisasi, langsung alihkan ke halaman hasil
    if submission.status in (
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.TIMED_OUT,
        SubmissionStatus.GRADED,
    ):
        return redirect(url_for("participant.result"))

    remaining_seconds = get_remaining_seconds(session_obj)

    # Jika waktu sesi sudah habis atau status FINISHED
    if effective_status.value == "FINISHED" or remaining_seconds <= 0:
        finalize_submission(submission, is_timeout=True)
        return redirect(url_for("participant.result"))

    all_questions = get_session_questions(session_obj)
    answers_map = get_submission_answers_map(submission.id)

    # Logika mode station (NORMAL vs MEMBER_ROTATION)
    is_member_rotation = (session_obj.station.mode == StationMode.MEMBER_ROTATION)
    member_count = current_app.config.get("MEMBER_ROTATION_COUNT", 3)

    if is_member_rotation:
        partitions = partition_questions_for_members(all_questions, member_count)
        active_questions = partitions.get(submission.current_member, [])
        current_member = submission.current_member
        total_members = member_count
    else:
        active_questions = all_questions
        current_member = 1
        total_members = 1

    submit_form = EmptyForm()
    member_form = EmptyForm()

    return render_template(
        "participant/quiz.html",
        station=station,
        group=group,
        team=team,
        competition_session=session_obj,
        submission=submission,
        questions=active_questions,
        total_all_questions=len(all_questions),
        answers_map=answers_map,
        remaining_seconds=remaining_seconds,
        is_member_rotation=is_member_rotation,
        current_member=current_member,
        total_members=total_members,
        submit_form=submit_form,
        member_form=member_form,
        ctx=ctx,
    )


@participant_bp.post("/quiz/submit")
@require_participant_stage("rules_accepted")
def quiz_submit():
    """Final submit seluruh jawaban tim pada sesi kuis aktif."""
    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Gagal mengirim jawaban: validasi token keamanan (CSRF) gagal.", "danger")
        return redirect(url_for("participant.quiz"))

    ctx = get_participant_context()
    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "danger")
        return redirect(url_for("participant.waiting"))

    from models import SubmissionStatus
    from services.quiz_service import get_or_create_submission
    from services.scoring_service import finalize_submission

    submission = get_or_create_submission(session_obj.id, ctx["team"].id)
    if submission.status in (
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.TIMED_OUT,
        SubmissionStatus.GRADED,
    ):
        return redirect(url_for("participant.result"))

    remaining_seconds = get_remaining_seconds(session_obj)
    is_timeout = (remaining_seconds <= 0)

    success, score, error_msg = finalize_submission(submission, is_timeout=is_timeout)
    if not success:
        flash(f"Gagal memproses penilaian: {error_msg}", "danger")
        return redirect(url_for("participant.quiz"))

    flash("Jawaban Anda telah berhasil dikirim dan dinilai oleh sistem!", "success")
    return redirect(url_for("participant.result"))


@participant_bp.post("/quiz/member-submit")
@require_participant_stage("rules_accepted")
def member_submit():
    """Submit bagian soal anggota pada mode MEMBER_ROTATION."""
    form = EmptyForm()
    if not form.validate_on_submit():
        flash("Token keamanan (CSRF) tidak valid.", "danger")
        return redirect(url_for("participant.quiz"))

    ctx = get_participant_context()
    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        return redirect(url_for("participant.waiting"))

    from models import SubmissionStatus
    from services.quiz_service import advance_member_rotation, get_or_create_submission
    from services.scoring_service import finalize_submission

    submission = get_or_create_submission(session_obj.id, ctx["team"].id)
    if submission.status != SubmissionStatus.IN_PROGRESS:
        return redirect(url_for("participant.result"))

    member_count = current_app.config.get("MEMBER_ROTATION_COUNT", 3)

    if submission.current_member < member_count:
        advance_member_rotation(submission, member_count)
        return redirect(url_for("participant.member_transition"))
    else:
        # Anggota terakhir selesai -> finalisasi submission
        remaining_seconds = get_remaining_seconds(session_obj)
        finalize_submission(submission, is_timeout=(remaining_seconds <= 0))
        return redirect(url_for("participant.result"))


@participant_bp.get("/quiz/member-transition")
@require_participant_stage("rules_accepted")
def member_transition():
    """Layar jeda/transisi fisik serah-terima perangkat antar-anggota tim."""
    ctx = get_participant_context()
    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        return redirect(url_for("participant.waiting"))

    from models import SubmissionStatus
    from services.quiz_service import get_or_create_submission

    submission = get_or_create_submission(session_obj.id, ctx["team"].id)
    if submission.status != SubmissionStatus.IN_PROGRESS:
        return redirect(url_for("participant.result"))

    member_count = current_app.config.get("MEMBER_ROTATION_COUNT", 3)
    remaining_seconds = get_remaining_seconds(session_obj)

    return render_template(
        "participant/member_transition.html",
        station=ctx["station"],
        group=ctx["group"],
        team=ctx["team"],
        competition_session=session_obj,
        submission=submission,
        completed_member=submission.current_member - 1,
        next_member=submission.current_member,
        total_members=member_count,
        remaining_seconds=remaining_seconds,
        ctx=ctx,
    )


@participant_bp.get("/result")
@require_participant_stage("rules_accepted")
def result():
    """
    Halaman hasil penilaian tim.
    Menampilkan perolehan nilai, jumlah benar, dan bonus waktu tanpa membocorkan kunci jawaban.
    """
    ctx = get_participant_context()
    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)

    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "danger")
        return redirect(url_for("participant.waiting"))

    from models import SubmissionStatus
    from services.quiz_service import get_or_create_submission
    from services.scoring_service import finalize_submission, get_submission_summary

    submission = get_or_create_submission(session_obj.id, ctx["team"].id)

    # Jika sesi sudah selesai atau waktu habis tetapi submission masih IN_PROGRESS, finalisasi sebagai TIMED_OUT
    effective_status = get_effective_status(session_obj)
    remaining_seconds = get_remaining_seconds(session_obj)
    if submission.status == SubmissionStatus.IN_PROGRESS and (
        effective_status.value == "FINISHED" or remaining_seconds <= 0
    ):
        finalize_submission(submission, is_timeout=True)

    if submission.status == SubmissionStatus.IN_PROGRESS:
        # Masih berjalan dan belum submit -> kembalikan ke kuis
        return redirect(url_for("participant.quiz"))

    summary = get_submission_summary(submission)

    return render_template(
        "participant/result.html",
        station=ctx["station"],
        group=ctx["group"],
        team=ctx["team"],
        competition_session=session_obj,
        submission=submission,
        summary=summary,
        ctx=ctx,
    )


@participant_bp.get("/leaderboard")
@require_participant_stage("rules_accepted")
def leaderboard():
    """
    Leaderboard hasil kuis pos lomba untuk peserta.
    Hanya dapat diakses setelah peserta menyelesaikan pengerjaan kuis timnya.
    """
    ctx = get_participant_context()
    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    if not session_obj:
        flash("Sesi perlombaan tidak ditemukan.", "danger")
        return redirect(url_for("participant.waiting"))

    from models import SubmissionStatus
    from services.leaderboard_service import get_session_leaderboard
    from services.quiz_service import get_or_create_submission

    submission = get_or_create_submission(session_obj.id, ctx["team"].id)

    # Peserta hanya boleh membuka leaderboard setelah kuis selesai
    effective_status = get_effective_status(session_obj)
    if submission.status == SubmissionStatus.IN_PROGRESS and effective_status.value != "FINISHED":
        flash("Selesaikan pengerjaan kuis terlebih dahulu untuk melihat leaderboard.", "warning")
        return redirect(url_for("participant.quiz"))

    leaderboard_data = get_session_leaderboard(session_obj.id)

    return render_template(
        "participant/leaderboard.html",
        station=ctx["station"],
        group=ctx["group"],
        team=ctx["team"],
        competition_session=session_obj,
        leaderboard=leaderboard_data,
        ctx=ctx,
    )


@participant_bp.get("/session-ended")
@require_participant_stage("rules_accepted")
def session_ended():
    ctx = get_participant_context()
    session_obj = find_participant_session(ctx["station"].id, ctx["group"].id)
    return render_template(
        "participant/session_ended.html",
        station=ctx["station"],
        group=ctx["group"],
        team=ctx["team"],
        competition_session=session_obj,
        ctx=ctx,
    )


@participant_bp.post("/reset")
def reset():
    form = EmptyForm()
    if form.validate_on_submit():
        clear_participant_session()
        flash("Sesi peserta telah direset. Silakan masuk kembali jika diperlukan.", "info")
    else:
        flash("Gagal melakukan reset sesi: token CSRF tidak valid.", "danger")
    return redirect(url_for("index"))
