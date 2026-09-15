from datetime import datetime
from flask import current_app

from models import Question, Score, Submission, SubmissionStatus, db
from services.session_service import get_remaining_seconds, get_server_now


def calculate_scores(
    submission: Submission,
    is_timeout: bool = False,
    current_time: datetime | None = None,
) -> Score:
    """
    Menghitung raw score, time bonus, dan final score untuk submission.
    Server bertindak sebagai pemegang kebenaran mutlak (Source of Truth).
    """
    now = current_time or get_server_now()
    session_obj = submission.session

    # Ambil seluruh soal aktif dari paket soal sesi lomba
    questions = db.session.scalars(
        db.select(Question)
        .where(
            Question.question_set_id == session_obj.question_set_id,
            Question.is_active.is_(True),
        )
        .order_by(Question.order_number.asc())
    ).all()

    answers_dict = {ans.question_id: ans for ans in submission.answers}
    raw_score = 0.0

    for q in questions:
        ans = answers_dict.get(q.id)
        if ans and ans.selected_answer:
            is_correct = ans.selected_answer.strip().upper() == q.correct_answer.strip().upper()
            points = float(q.weight) if is_correct else 0.0
            ans.is_correct = is_correct
            ans.points_awarded = points
            raw_score += points
        elif ans:
            ans.is_correct = False
            ans.points_awarded = 0.0

    raw_score = round(raw_score, 2)

    # Hitung Time Bonus
    if is_timeout:
        time_bonus = 0.0
    else:
        remaining = get_remaining_seconds(session_obj, now)
        if remaining <= 0:
            time_bonus = 0.0
        else:
            bonus_per_second = float(current_app.config.get("TIME_BONUS_PER_SECOND", 1.0))
            time_bonus = round(remaining * bonus_per_second, 2)

    final_score = round(raw_score + time_bonus, 2)

    # Upsert objek Score
    score_obj = db.session.scalar(
        db.select(Score).where(Score.submission_id == submission.id)
    )
    if score_obj:
        score_obj.raw_score = raw_score
        score_obj.time_bonus = time_bonus
        score_obj.final_score = final_score
        score_obj.submitted_at = now
    else:
        score_obj = Score(
            submission_id=submission.id,
            raw_score=raw_score,
            time_bonus=time_bonus,
            final_score=final_score,
            submitted_at=now,
        )
        db.session.add(score_obj)

    return score_obj


def finalize_submission(
    submission: Submission,
    is_timeout: bool = False,
    current_time: datetime | None = None,
) -> tuple[bool, Score | None, str | None]:
    """
    Memfinalisasi submission peserta (baik submit manual maupun auto-timeout).
    Idempoten: jika sudah pernah difinalisasi, langsung mengembalikan Score yang ada.
    """
    now = current_time or get_server_now()

    # Double submit protection
    if submission.status in (
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.TIMED_OUT,
        SubmissionStatus.GRADED,
    ):
        score_obj = db.session.scalar(
            db.select(Score).where(Score.submission_id == submission.id)
        )
        return True, score_obj, "Submission sudah pernah difinalisasi sebelumnya."

    try:
        # Hitung skor dan perbarui status submission
        score_obj = calculate_scores(submission, is_timeout, now)
        submission.status = SubmissionStatus.TIMED_OUT if is_timeout else SubmissionStatus.SUBMITTED
        submission.submitted_at = now

        db.session.commit()
        return True, score_obj, None
    except Exception as e:
        db.session.rollback()
        return False, None, f"Gagal memfinalisasi submission: {str(e)}"


def get_submission_summary(submission: Submission) -> dict:
    """
    Mengambil ringkasan hasil submission untuk tampilan peserta.
    PENTING: Tidak pernah membocorkan kunci jawaban atau status benar/salah per butir soal.
    """
    session_obj = submission.session
    total_questions = db.session.scalar(
        db.select(db.func.count())
        .select_from(Question)
        .where(
            Question.question_set_id == session_obj.question_set_id,
            Question.is_active.is_(True),
        )
    ) or 0

    answers = submission.answers
    correct_count = sum(1 for ans in answers if ans.is_correct is True)
    answered_count = sum(1 for ans in answers if ans.selected_answer is not None)
    unanswered_count = max(0, total_questions - answered_count)

    score_obj = submission.score

    return {
        "team_name": submission.team.team_name,
        "team_code": submission.team.team_code,
        "school": submission.team.school,
        "station_name": session_obj.station.name,
        "group_code": session_obj.group.code,
        "total_questions": total_questions,
        "answered_count": answered_count,
        "unanswered_count": unanswered_count,
        "correct_count": correct_count,
        "raw_score": score_obj.raw_score if score_obj else 0.0,
        "time_bonus": score_obj.time_bonus if score_obj else 0.0,
        "final_score": score_obj.final_score if score_obj else 0.0,
        "status": submission.status.value,
        "submitted_at": score_obj.submitted_at if score_obj else submission.submitted_at,
    }
