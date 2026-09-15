from flask import current_app
from sqlalchemy.exc import IntegrityError

from models import (
    Answer,
    CompetitionSession,
    Question,
    StationMode,
    Submission,
    SubmissionStatus,
    db,
)
from services.session_service import get_server_now


def get_or_create_submission(session_id: int, team_id: int) -> Submission:
    """
    Mengambil atau membuat objek Submission untuk tim pada sesi tertentu.
    Aman dari race condition duplicate menggunakan try/except IntegrityError.
    """
    existing = db.session.scalar(
        db.select(Submission).where(
            Submission.session_id == session_id,
            Submission.team_id == team_id,
        )
    )
    if existing:
        return existing

    server_now = get_server_now()
    new_submission = Submission(
        session_id=session_id,
        team_id=team_id,
        status=SubmissionStatus.IN_PROGRESS,
        current_member=1,
        started_at=server_now,
    )
    db.session.add(new_submission)
    try:
        db.session.commit()
        return new_submission
    except IntegrityError:
        db.session.rollback()
        # Jika terjadi balapan antar-request, ambil submission yang sudah dibuat
        return db.session.scalar(
            db.select(Submission).where(
                Submission.session_id == session_id,
                Submission.team_id == team_id,
            )
        )


def get_session_questions(session_obj: CompetitionSession) -> list[Question]:
    """Mengambil seluruh butir soal aktif dari paket soal sesi lomba, terurut order_number ASC."""
    return db.session.scalars(
        db.select(Question)
        .where(
            Question.question_set_id == session_obj.question_set_id,
            Question.is_active.is_(True),
        )
        .order_by(Question.order_number.asc())
    ).all()


def partition_questions_for_members(
    questions: list[Question], member_count: int
) -> dict[int, list[Question]]:
    """
    Membagi daftar soal secara deterministik dan merata kepada setiap anggota tim (1..member_count).
    Tidak ada soal yang hilang atau terduplikasi.
    """
    total = len(questions)
    k = max(1, member_count)
    partitions: dict[int, list[Question]] = {}
    start_idx = 0

    for i in range(k):
        member_num = i + 1
        # Bagikan sisa secara merata ke anggota-anggota awal
        size = (total // k) + (1 if i < (total % k) else 0)
        partitions[member_num] = questions[start_idx : start_idx + size]
        start_idx += size

    return partitions


def get_submission_answers_map(submission_id: int) -> dict[int, str]:
    """Mengembalikan peta {question_id: selected_answer} yang sudah disimpan di database."""
    answers = db.session.scalars(
        db.select(Answer).where(Answer.submission_id == submission_id)
    ).all()
    return {ans.question_id: ans.selected_answer for ans in answers if ans.selected_answer}


def save_answer(
    submission: Submission, question_id: int, selected_answer: str
) -> tuple[bool, str | None]:
    """
    Menyimpan atau memperbarui jawaban peserta (Upsert).
    Validasi ketat:
    1. Submission harus berstatus IN_PROGRESS.
    2. Selected answer harus dalam ('A', 'B', 'C', 'D').
    3. Soal harus aktif dan termasuk dalam QuestionSet sesi lomba.
    4. Jika mode MEMBER_ROTATION, soal harus dialokasikan untuk current_member yang aktif.
    """
    if submission.status != SubmissionStatus.IN_PROGRESS:
        return False, "Sesi pengerjaan sudah selesai atau tidak aktif."

    answer_val = str(selected_answer).strip().upper()
    if answer_val not in ("A", "B", "C", "D"):
        return False, "Pilihan jawaban tidak valid (harus A, B, C, atau D)."

    question = db.session.get(Question, question_id)
    if not question or not question.is_active:
        return False, "Soal tidak ditemukan atau sudah dinonaktifkan."

    if question.question_set_id != submission.session.question_set_id:
        return False, "Soal tidak termasuk dalam paket soal sesi lomba ini."

    # Validasi pembagian anggota jika mode MEMBER_ROTATION
    if submission.session.station.mode == StationMode.MEMBER_ROTATION:
        member_count = current_app.config.get("MEMBER_ROTATION_COUNT", 3)
        all_q = get_session_questions(submission.session)
        partitions = partition_questions_for_members(all_q, member_count)
        allowed_q_ids = {q.id for q in partitions.get(submission.current_member, [])}
        if question_id not in allowed_q_ids:
            return False, f"Soal ini bukan merupakan bagian dari giliran Anggota {submission.current_member}."

    # Upsert jawaban
    existing_answer = db.session.scalar(
        db.select(Answer).where(
            Answer.submission_id == submission.id,
            Answer.question_id == question_id,
        )
    )

    if existing_answer:
        existing_answer.selected_answer = answer_val
    else:
        new_answer = Answer(
            submission_id=submission.id,
            question_id=question_id,
            selected_answer=answer_val,
        )
        db.session.add(new_answer)

    try:
        db.session.commit()
        return True, None
    except IntegrityError:
        db.session.rollback()
        # Penanganan benturan konkurensi: baris telah dibuat oleh request bersamaan
        existing_answer = db.session.scalar(
            db.select(Answer).where(
                Answer.submission_id == submission.id,
                Answer.question_id == question_id,
            )
        )
        if existing_answer:
            existing_answer.selected_answer = answer_val
            try:
                db.session.commit()
                return True, None
            except Exception as e2:
                db.session.rollback()
                return False, f"Gagal menyimpan jawaban: {str(e2)}"
        return False, "Gagal menyimpan jawaban karena benturan data."
    except Exception as e:
        db.session.rollback()
        return False, f"Gagal menyimpan jawaban: {str(e)}"


def advance_member_rotation(
    submission: Submission, member_count: int
) -> tuple[bool, str | None]:
    """Memajukan giliran anggota pada mode MEMBER_ROTATION."""
    if submission.status != SubmissionStatus.IN_PROGRESS:
        return False, "Sesi pengerjaan sudah tidak aktif."

    if submission.current_member < member_count:
        submission.current_member += 1
        try:
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, f"Gagal memajukan anggota: {str(e)}"

    return False, "Seluruh anggota tim telah menyelesaikan bagiannya."
