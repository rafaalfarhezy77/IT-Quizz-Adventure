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
