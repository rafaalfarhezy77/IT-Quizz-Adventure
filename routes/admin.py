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
from werkzeug.security import check_password_hash

from forms.admin import LoginForm
from forms.question import (
    EmptyForm,
    QuestionForm,
    QuestionImportConfirmForm,
    QuestionJSONUploadForm,
    QuestionSetStatusForm,
)
from forms.session import SessionActionForm, SessionForm
from forms.team import TeamCSVUploadForm, TeamForm, TeamImportConfirmForm
from models import (
    Admin,
    CompetitionSession,
    Group,
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
    return None


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.current_admin is not None:
        return redirect(url_for("admin.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        admin = db.session.scalar(db.select(Admin).where(Admin.username == username))
        if admin and admin.is_active and check_password_hash(admin.password_hash, form.password.data):
            session.clear()
            session["admin_id"] = admin.id
            flash("Login berhasil.", "success")
            return redirect(url_for("admin.dashboard"))
        flash("Username atau password salah.", "error")
    return render_template("admin/login.html", form=form)


@admin_bp.post("/logout")
@admin_required
def logout():
    session.clear()
    flash("Anda telah logout.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    statistics = {
        "stations": db.session.scalar(db.select(db.func.count()).select_from(Station)),
        "groups": db.session.scalar(db.select(db.func.count()).select_from(Group)),
        "teams": db.session.scalar(db.select(db.func.count()).select_from(Team).where(Team.is_active.is_(True))),
        "questions": db.session.scalar(db.select(db.func.count()).select_from(Question).where(Question.is_active.is_(True))),
        "active_sessions": db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.status == SessionStatus.RUNNING)),
        "finished_sessions": db.session.scalar(db.select(db.func.count()).select_from(CompetitionSession).where(CompetitionSession.status == SessionStatus.FINISHED)),
        "total_submissions": db.session.scalar(db.select(db.func.count()).select_from(Submission).where(Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED)))),
    }
    return render_template("admin/dashboard.html", statistics=statistics)


# ==============================================================================
# MANAJEMEN SOAL (LANGKAH 3)
# ==============================================================================

@admin_bp.get("/questions")
@admin_required
def questions_index():
    """Daftar seluruh question set dikelompokkan berdasarkan station aktif."""
    ensure_default_question_sets()

    selected_station_id = request.args.get("station_id", type=int)

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

    if selected_station_id:
        stations = [s for s in all_stations if s.id == selected_station_id]
    else:
        stations = all_stations

    return render_template(
        "admin/questions/index.html",
        stations=stations,
        all_stations=all_stations,
        selected_station_id=selected_station_id,
    )


@admin_bp.get("/questions/set/<int:set_id>")
@admin_required
def question_set_detail(set_id: int):
    """Detail satu question set, menampilkan daftar soal, filter, dan kontrol status."""
    question_set = db.session.get(QuestionSet, set_id)
    if question_set is None:
        abort(404)

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


@admin_bp.post("/questions/<int:question_id>/delete")
@admin_required
def question_delete(question_id: int):
    """Soft delete soal (is_active = False)."""
    question = db.session.get(Question, question_id)
    if question is None:
        abort(404)

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
    empty_form = EmptyForm()

    return render_template(
        "admin/teams/index.html",
        teams=teams,
        groups=groups,
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
    active_stations = db.session.scalars(
        db.select(Station).where(Station.is_active.is_(True)).order_by(Station.name)
    ).all()
    form.station_id.choices = [
        (s.id, f"{s.name} ({'BELUM DIKETAHUI' if s.mode == StationMode.BELUM_DIKETAHUI else s.mode.value})")
        for s in active_stations
    ]

    groups = db.session.scalars(db.select(Group).order_by(Group.code)).all()
    form.group_id.choices = [(g.id, f"Kelompok {g.code}") for g in groups]

    ready_sets = db.session.scalars(
        db.select(QuestionSet)
        .join(Station)
        .where(QuestionSet.status == QuestionSetStatus.READY)
        .order_by(Station.name, QuestionSet.code)
    ).all()
    form.question_set_id.choices = [
        (qs.id, f"{qs.station.name} — Set {qs.code} ({qs.name})") for qs in ready_sets
    ]


@admin_bp.get("/sessions")
@admin_required
def sessions_index():
    sessions = db.session.scalars(
        db.select(CompetitionSession).order_by(CompetitionSession.created_at.desc())
    ).all()

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
    return render_template("admin/sessions/index.html", sessions=session_data, action_form=action_form)


@admin_bp.route("/sessions/create", methods=["GET", "POST"])
@admin_required
def sessions_create():
    form = SessionForm()
    _populate_session_form_choices(form)

    if form.validate_on_submit():
        try:
            new_session = create_session(
                station_id=form.station_id.data,
                group_id=form.group_id.data,
                question_set_id=form.question_set_id.data,
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
                question_set_id=form.question_set_id.data,
                duration_minutes=form.duration_minutes.data,
            )
            flash("Data sesi berhasil diperbarui.", "success")
            return redirect(url_for("admin.sessions_detail", session_id=session_obj.id))
        except ValueError as e:
            flash(str(e), "error")
    elif request.method == "GET":
        form.station_id.data = session_obj.station_id
        form.group_id.data = session_obj.group_id
        form.question_set_id.data = session_obj.question_set_id
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
