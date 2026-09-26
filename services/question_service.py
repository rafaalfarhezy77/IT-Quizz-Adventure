from models import (
    CompetitionSession,
    Question,
    QuestionSet,
    QuestionSetStatus,
    SessionStatus,
    Station,
    StationMode,
    db,
)


def ensure_default_question_sets():
    """Memastikan setiap pos/station aktif yang modenya sudah terdefinisi memiliki Question Set A, B, C, dan D secara idempotent."""
    stations = db.session.scalars(
        db.select(Station)
        .where(
            Station.is_active.is_(True),
            Station.mode != StationMode.BELUM_DIKETAHUI,
        )
        .order_by(Station.id)
    ).all()
    created_any = False
    for station in stations:
        for code in ("A", "B", "C", "D"):
            existing = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == station.id,
                    QuestionSet.code == code,
                )
            )
            if existing is None:
                db.session.add(
                    QuestionSet(
                        station_id=station.id,
                        code=code,
                        name=f"Set {code}",
                        status=QuestionSetStatus.DRAFT,
                    )
                )
                created_any = True
    if created_any:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise


def is_question_set_editable(question_set: QuestionSet) -> tuple[bool, str | None]:
    """
    Memeriksa apakah question set boleh dimodifikasi (tambah, edit, delete, restore).
    Menolak jika status LOCKED atau ada sesi RUNNING yang menggunakannya.
    """
    if question_set.status == QuestionSetStatus.LOCKED:
        return False, "Question set sedang dikunci (LOCKED) dan tidak dapat dimodifikasi."

    # Cek apakah set sedang digunakan oleh sesi yang sedang berjalan (RUNNING)
    running_session = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.question_set_id == question_set.id,
            CompetitionSession.status == SessionStatus.RUNNING,
        )
    )
    if running_session is not None:
        return False, "Question set sedang digunakan pada sesi lomba yang sedang berjalan."

    return True, None


def validate_question_set_ready(question_set: QuestionSet) -> tuple[bool, list[str]]:
    """
    Validasi kelayakan sebelum status question set diubah ke READY.
    Syarat:
    1. Memiliki minimal 1 soal aktif.
    2. Semua soal aktif memiliki pilihan A, B, C, D yang terisi.
    3. Semua soal aktif memiliki kunci jawaban yang valid (A, B, C, D).
    4. Semua soal aktif memiliki bobot nilai positif (> 0).
    5. Semua soal aktif memiliki nomor urut yang valid (>= 1).
    """
    errors: list[str] = []
    active_questions = [q for q in question_set.questions if q.is_active]

    if not active_questions:
        errors.append("Question set belum memiliki soal aktif.")
        return False, errors

    if question_set.station.name.lower() == "networking":
        if sorted(q.order_number for q in active_questions) != list(range(1, 26)):
            errors.append("Networking wajib memiliki 25 soal bernomor 1–25.")
        for q in active_questions:
            errors.extend(validate_networking_question(q))
        return not errors, errors

    for q in active_questions:
        prefix = f"Soal nomor urut #{q.order_number}"
        if not q.text or not q.text.strip():
            errors.append(f"{prefix}: teks pertanyaan masih kosong.")
        if not q.option_a or not q.option_a.strip():
            errors.append(f"{prefix}: pilihan A belum diisi.")
        if not q.option_b or not q.option_b.strip():
            errors.append(f"{prefix}: pilihan B belum diisi.")
        if not q.option_c or not q.option_c.strip():
            errors.append(f"{prefix}: pilihan C belum diisi.")
        if not q.option_d or not q.option_d.strip():
            errors.append(f"{prefix}: pilihan D belum diisi.")
        if q.correct_answer not in ("A", "B", "C", "D"):
            errors.append(f"{prefix}: kunci jawaban ({q.correct_answer}) tidak valid (harus A/B/C/D).")
        if q.weight is None or q.weight <= 0:
            errors.append(f"{prefix}: bobot nilai ({q.weight}) harus lebih dari 0.")
        if q.order_number is None or q.order_number < 1:
            errors.append(f"{prefix}: nomor urut ({q.order_number}) harus minimal 1.")

    return (len(errors) == 0), errors


def get_next_order_number(question_set_id: int) -> int:
    """Mengembalikan nomor urut soal berikutnya untuk set tertentu."""
    max_order = db.session.scalar(
        db.select(db.func.max(Question.order_number)).where(
            Question.question_set_id == question_set_id
        )
    )
    return (max_order or 0) + 1


def is_order_number_taken(question_set_id: int, order_number: int, exclude_question_id: int | None = None) -> bool:
    """Mengecek apakah order_number sudah terpakai oleh soal lain dalam set yang sama."""
    stmt = db.select(Question).where(
        Question.question_set_id == question_set_id,
        Question.order_number == order_number,
    )
    if exclude_question_id is not None:
        stmt = stmt.where(Question.id != exclude_question_id)
    return db.session.scalar(stmt) is not None


def validate_networking_question(q):
    """Validate stage, answer key and exact 30/40/30 scoring contract."""
    import math
    errors = []
    stage = 1 if 1 <= q.order_number <= 10 else 2 if 11 <= q.order_number <= 20 else 3
    kind = {1: "multiple_choice", 2: "true_false", 3: "short_text"}[stage]
    if not 1 <= q.order_number <= 25 or q.stage != stage or q.question_type != kind:
        errors.append("Nomor, tahap, dan tipe soal Networking tidak sesuai (1–10 PG, 11–20 B/S, 21–25 isian).")
    if not q.text or not q.text.strip():
        errors.append("Teks soal wajib diisi.")
    if not math.isfinite(float(q.weight or 0)) or q.weight != {1: 3, 2: 4, 3: 6}[stage]:
        errors.append("Bobot Networking wajib 3/4/6 sesuai tahap.")
    if stage == 1:
        if any(not getattr(q, "option_"+k.lower(), None) for k in "ABCDE") or q.correct_answer not in "ABCDE" or len(q.correct_answer) != 1:
            errors.append("Pilihan A–E dan kunci A–E wajib diisi.")
    elif stage == 2:
        if str(q.correct_answer).lower() not in ("benar", "salah", "true", "false", "b", "s", "t", "f"):
            errors.append("Kunci harus Benar atau Salah.")
    elif not q.correct_answer or not isinstance(q.accepted_answers, list) or any(not isinstance(a, str) or not a.strip() for a in q.accepted_answers):
        errors.append("Kunci utama dan daftar varian teks wajib valid.")
    if stage in (2, 3) and any(getattr(q, "option_" + letter, None) for letter in "abcde"):
        errors.append("Benar/Salah dan isian singkat tidak memakai opsi A–E.")
    if (q.order_number in (18, 19) or stage == 3) and not str(getattr(q, "case_study", "") or "").strip():
        errors.append("Studi kasus wajib diisi untuk Tahap 2 nomor 8/9 dan seluruh soal Tahap 3.")
    return errors
