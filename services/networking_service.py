"""
Networking Service for Mythic 3.0 IT Quiz Adventure.
Handles 3-stage quiz challenge, text normalization, exact evaluation,
facilitator review queue, Stamp verification (Tahap 3 >= 4 of 5),
server-authoritative timers, and facilitator controls with complete audit logging.
"""
import re
from datetime import datetime, timezone
from typing import Any

from flask import current_app
from sqlalchemy.orm import joinedload

from models import (
    Admin,
    Answer,
    CompetitionSession,
    NetworkingSubmission,
    NetworkingSubmissionAudit,
    Question,
    QuestionSet,
    QuestionSetStatus,
    Score,
    SessionStatus,
    Submission,
    SubmissionStatus,
    Team,
    db,
    utcnow,
)
from services.session_service import get_server_now, get_remaining_seconds, ensure_naive_utc


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Memastikan datetime selalu memiliki tzinfo timezone.utc agar perbandingan aman."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_text_answer(text: str | None) -> str:
    """Only normalize case and whitespace; punctuation remains significant."""
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def evaluate_short_text_answer(
    user_text: str | None,
    accepted_answers: list[str] | None,
) -> tuple[bool, str]:
    """
    Mengevaluasi jawaban isian singkat terhadap daftar accepted_answers.
    Jika cocok dengan salah satu varian -> (True, 'AUTO_GRADED').
    Jika tidak cocok -> (False, 'NEEDS_REVIEW') agar masuk antrean peninjauan juri.
    """
    norm_user = normalize_text_answer(user_text)
    if not norm_user:
        return False, "NEEDS_REVIEW"

    if not accepted_answers:
        return False, "NEEDS_REVIEW"

    for accepted in accepted_answers:
        if norm_user == normalize_text_answer(accepted):
            return True, "AUTO_GRADED"

    return False, "NEEDS_REVIEW"


def get_or_create_networking_submission(
    session_id: int,
    team_id: int,
    client_token: str | None = None,
) -> tuple[Submission, NetworkingSubmission, bool]:
    """
    Mengambil atau membuat entitas Submission dan NetworkingSubmission.
    Mendeteksi konkurensi / sesi ganda:
    Mengembalikan (submission, net_sub, is_token_conflict).
    """
    sub = db.session.scalar(
        db.select(Submission).where(
            Submission.session_id == session_id,
            Submission.team_id == team_id,
        )
    )

    is_new = False
    now = utcnow()
    competition = db.session.get(CompetitionSession, session_id)
    team = db.session.get(Team, team_id)
    if not competition or competition.station.name.lower() != "networking" or not team or team.group_id != competition.group_id:
        raise ValueError("Tim atau sesi Networking tidak sesuai kelompok.")

    if not sub:
        sub = Submission(
            session_id=session_id,
            team_id=team_id,
            submission_type="networking",
            status=SubmissionStatus.IN_PROGRESS,
            current_member=1,
            started_at=now,
        )
        db.session.add(sub)
        db.session.flush()
        is_new = True

    net_sub = db.session.scalar(
        db.select(NetworkingSubmission).where(
            NetworkingSubmission.submission_id == sub.id
        )
    )

    if not net_sub:
        net_sub = NetworkingSubmission(
            submission_id=sub.id,
            current_stage=1,
            stage_1_duration_seconds=current_app.config.get("NETWORKING_STAGE_1_SECONDS", 600),
            stage_2_duration_seconds=current_app.config.get("NETWORKING_STAGE_2_SECONDS", 300),
            stage_3_duration_seconds=current_app.config.get("NETWORKING_STAGE_3_SECONDS", 900),
            stage_1_started_at=competition.started_at or now,
            verification_status="IN_PROGRESS",
            session_token=client_token,
        )
        db.session.add(net_sub)
        db.session.commit()
        return sub, net_sub, False

    # Check token conflict (pencegahan 2 sesi aktif bersamaan)
    token_conflict = False
    if client_token and net_sub.session_token:
        if net_sub.session_token != client_token and net_sub.verification_status in (
            "IN_PROGRESS",
            "READY",
            "LOBBY",
        ):
            token_conflict = True
    elif client_token and not net_sub.session_token:
        net_sub.session_token = client_token
        db.session.commit()

    return sub, net_sub, token_conflict


def get_stage_questions(session_obj: CompetitionSession, stage_num: int) -> list[Question]:
    """
    Mengambil daftar butir soal aktif untuk tahap tertentu (1, 2, atau 3) dari paket soal sesi.
    Jika kolom stage telah diisi, filter berdasarkan Question.stage == stage_num.
    Jika belum, fallback deterministik:
    Tahap 1: order_number 1..10
    Tahap 2: order_number 11..20
    Tahap 3: order_number 21..25
    """
    all_questions = db.session.scalars(
        db.select(Question)
        .where(
            Question.question_set_id == session_obj.question_set_id,
            Question.is_active.is_(True),
        )
        .order_by(Question.order_number.asc())
    ).all()

    # Cek apakah kolom stage digunakan
    has_explicit_stage = any(q.stage == stage_num for q in all_questions)
    if has_explicit_stage:
        return [q for q in all_questions if q.stage == stage_num]

    # Fallback berurutan
    if stage_num == 1:
        return [q for q in all_questions if 1 <= q.order_number <= 10]
    elif stage_num == 2:
        return [q for q in all_questions if 11 <= q.order_number <= 20]
    elif stage_num == 3:
        return [q for q in all_questions if 21 <= q.order_number <= 25]
    return []


def get_stage_timer_info(net_sub: NetworkingSubmission, stage_num: int) -> dict[str, Any]:
    """
    Menghitung status timer berbasis server untuk tahap tertentu.
    Sumber kebenaran adalah waktu server.
    """
    now = ensure_utc(utcnow())
    if stage_num == 1:
        started_at = ensure_utc(net_sub.stage_1_started_at)
        submitted_at = ensure_utc(net_sub.stage_1_submitted_at)
        duration = net_sub.stage_1_duration_seconds
    elif stage_num == 2:
        started_at = ensure_utc(net_sub.stage_2_started_at)
        submitted_at = ensure_utc(net_sub.stage_2_submitted_at)
        duration = net_sub.stage_2_duration_seconds
    elif stage_num == 3:
        started_at = ensure_utc(net_sub.stage_3_started_at)
        submitted_at = ensure_utc(net_sub.stage_3_submitted_at)
        duration = net_sub.stage_3_duration_seconds
    else:
        return {
            "stage": stage_num,
            "duration_seconds": 0,
            "remaining_seconds": 0,
            "is_locked": True,
            "is_expired": True,
        }

    is_locked = submitted_at is not None

    if not started_at:
        remaining = duration
        is_expired = False
    else:
        elapsed = (now - started_at).total_seconds()
        remaining = max(0, int(duration - elapsed))
        remaining = min(remaining, get_remaining_seconds(net_sub.submission.session, ensure_naive_utc(now)))
        is_expired = remaining <= 0

    return {
        "stage": stage_num,
        "started_at": started_at.isoformat() if started_at else None,
        "submitted_at": submitted_at.isoformat() if submitted_at else None,
        "duration_seconds": duration,
        "remaining_seconds": remaining,
        "is_locked": is_locked or is_expired,
        "is_expired": is_expired,
    }


def save_networking_answer(
    submission_id: int,
    question_id: int,
    raw_answer: str | None,
) -> tuple[bool, str | None, str | None]:
    """
    Menyimpan jawaban peserta untuk Pos Networking (Upsert).
    Otomatis mengevaluasi jawaban sesuai tipe soal:
    - multiple_choice: validasi A–E, auto-grade langsung.
    - true_false: validasi Benar/Salah, auto-grade langsung.
    - short_text: normalisasi teks & cocokkan accepted_answers.
      Jika cocok -> AUTO_GRADED, jika tidak -> NEEDS_REVIEW.
    Mengembalikan (success, error_msg, review_status)
    """
    net_sub = db.session.scalar(
        db.select(NetworkingSubmission).where(
            NetworkingSubmission.submission_id == submission_id
        )
    )
    if not net_sub:
        return False, "Submission networking tidak ditemukan.", None

    sub = net_sub.submission
    if sub.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED):
        return False, "Sesi pengerjaan sudah dikumpulkan atau selesai.", None

    question = db.session.get(Question, question_id)
    if not question or not question.is_active:
        return False, "Soal tidak valid atau dinonaktifkan.", None

    # Validasi bahwa soal termasuk dalam set soal sesi ini
    if sub.session and sub.session.question_set_id:
        if question.question_set_id != sub.session.question_set_id:
            return False, "Soal tidak termasuk dalam paket soal sesi ini.", None

    # Tentukan tahap soal
    stage_num = question.stage if question.stage in (1, 2, 3) else (
        1 if question.order_number <= 10 else (2 if question.order_number <= 20 else 3)
    )

    # Periksa apakah tahap ini masih aktif
    if net_sub.current_stage != stage_num:
        return False, f"Tahap {stage_num} sudah terkunci atau belum aktif.", None

    timer_info = get_stage_timer_info(net_sub, stage_num)
    if timer_info["is_locked"]:
        return False, f"Waktu pengerjaan Tahap {stage_num} sudah habis atau terkunci.", None

    # Parsing dan evaluasi nilai jawaban
    selected_answer = None
    text_answer = None
    is_correct = False
    points_awarded = 0.0
    review_status = "AUTO_GRADED"

    q_type = question.question_type or "multiple_choice"

    if q_type == "multiple_choice":
        clean_ans = str(raw_answer or "").strip().upper()
        if clean_ans not in ("A", "B", "C", "D", "E"):
            return False, "Pilihan jawaban harus salah satu dari A, B, C, D, atau E.", None
        selected_answer = clean_ans
        text_answer = clean_ans
        is_correct = (clean_ans == question.correct_answer.strip().upper())
        points_awarded = float(question.weight) if is_correct else 0.0

    elif q_type == "true_false":
        clean_ans = str(raw_answer or "").strip()
        # Normalisasi ke "Benar" / "Salah"
        if clean_ans.lower() in ("benar", "true", "b", "t"):
            normalized_val = "Benar"
        elif clean_ans.lower() in ("salah", "false", "s", "f"):
            normalized_val = "Salah"
        else:
            return False, "Pilihan jawaban harus bernilai 'Benar' atau 'Salah'.", None

        selected_answer = normalized_val
        text_answer = normalized_val
        q_correct = question.correct_answer.strip()
        if q_correct.lower() in ("benar", "true", "b", "t"):
            corr_norm = "Benar"
        else:
            corr_norm = "Salah"
        is_correct = (normalized_val == corr_norm)
        points_awarded = float(question.weight) if is_correct else 0.0

    elif q_type == "short_text":
        user_text = str(raw_answer or "").strip()
        selected_answer = user_text[:255]
        text_answer = user_text
        matched, status = evaluate_short_text_answer(user_text, [question.correct_answer] + (question.accepted_answers or []))
        is_correct = matched
        points_awarded = float(question.weight) if matched else 0.0
        review_status = status

    # Upsert entitas Answer
    ans = db.session.scalar(
        db.select(Answer).where(
            Answer.submission_id == sub.id,
            Answer.question_id == question.id,
        )
    )

    if ans:
        ans.selected_answer = selected_answer
        ans.text_answer = text_answer
        ans.is_correct = is_correct
        ans.points_awarded = points_awarded
        ans.review_status = review_status
    else:
        ans = Answer(
            submission_id=sub.id,
            question_id=question.id,
            selected_answer=selected_answer,
            text_answer=text_answer,
            is_correct=is_correct,
            points_awarded=points_awarded,
            review_status=review_status,
        )
        db.session.add(ans)

    try:
        db.session.commit()
        return True, None, review_status
    except Exception as ex:
        db.session.rollback()
        return False, f"Gagal menyimpan jawaban: {str(ex)}", None


def calculate_stage_score(net_sub: NetworkingSubmission, stage_num: int) -> float:
    """Menghitung perolehan poin dari jawaban peserta pada tahap tertentu."""
    sub = net_sub.submission
    questions = get_stage_questions(sub.session, stage_num)
    q_ids = {q.id for q in questions}

    answers = db.session.scalars(
        db.select(Answer).where(
            Answer.submission_id == sub.id,
            Answer.question_id.in_(q_ids),
        )
    ).all()

    total_pts = sum(float(a.points_awarded or 0.0) for a in answers if a.is_correct)
    return round(total_pts, 2)


def submit_stage(
    submission_id: int,
    stage_num: int,
    is_timeout: bool = False,
) -> tuple[bool, str | None, int]:
    """
    Mengunci tahap saat ini dan beralih ke tahap berikutnya atau final submission.
    Tahap 1 -> Tahap 2
    Tahap 2 -> Tahap 3
    Tahap 3 -> Tahap 4 (Selesai pengerjaan kuis, masuk antrean verifikasi)
    Mengembalikan (success, error_msg, next_stage).
    """
    net_sub = db.session.scalar(
        db.select(NetworkingSubmission).where(
            NetworkingSubmission.submission_id == submission_id
        )
    )
    if not net_sub:
        return False, "Data submission networking tidak ditemukan.", stage_num

    sub = net_sub.submission
    if net_sub.current_stage != stage_num or sub.status != SubmissionStatus.IN_PROGRESS:
        return False, "Tahap sudah terkunci atau belum aktif.", net_sub.current_stage
    is_timeout = is_timeout or get_stage_timer_info(net_sub, stage_num)["is_expired"]
    now = utcnow()

    if stage_num == 1:
        if net_sub.stage_1_submitted_at is None:
            net_sub.stage_1_submitted_at = now
        net_sub.stage_1_score = calculate_stage_score(net_sub, 1)
        net_sub.current_stage = 2
        if not net_sub.stage_2_started_at:
            net_sub.stage_2_started_at = now
        db.session.commit()
        return True, None, 2

    elif stage_num == 2:
        if net_sub.stage_2_submitted_at is None:
            net_sub.stage_2_submitted_at = now
        net_sub.stage_2_score = calculate_stage_score(net_sub, 2)
        net_sub.current_stage = 3
        if not net_sub.stage_3_started_at:
            net_sub.stage_3_started_at = now
        db.session.commit()
        return True, None, 3

    elif stage_num == 3:
        if net_sub.stage_3_submitted_at is None:
            net_sub.stage_3_submitted_at = now
        net_sub.stage_3_score = calculate_stage_score(net_sub, 3)

        # Hitung jumlah jawaban benar Tahap 3
        questions_s3 = get_stage_questions(sub.session, 3)
        q3_ids = {q.id for q in questions_s3}
        ans_s3 = db.session.scalars(
            db.select(Answer).where(
                Answer.submission_id == sub.id,
                Answer.question_id.in_(q3_ids),
            )
        ).all()
        correct_count = sum(1 for a in ans_s3 if a.is_correct)
        net_sub.stage_3_correct_count = correct_count
        net_sub.has_stamp = (correct_count >= 4)

        # Cek apakah ada jawaban short_text yang butuh verifikasi juri
        has_needs_review = any(a.review_status == "NEEDS_REVIEW" for a in ans_s3)
        if has_needs_review:
            net_sub.verification_status = "NEEDS_REVIEW"
        else:
            net_sub.verification_status = "SUBMITTED"

        net_sub.current_stage = 4
        sub.status = SubmissionStatus.SUBMITTED if not is_timeout else SubmissionStatus.TIMED_OUT
        sub.submitted_at = now
        remaining = get_remaining_seconds(sub.session, ensure_naive_utc(now))
        net_sub.time_bonus = 0.0 if is_timeout else round(remaining * float(current_app.config.get("TIME_BONUS_PER_SECOND", 1.0)), 2)

        # Hitung skor sementara
        net_sub.provisional_score = round(
            net_sub.stage_1_score + net_sub.stage_2_score + net_sub.stage_3_score, 2
        )
        db.session.commit()
        return True, None, 4

    return False, "Nomor tahap tidak valid.", stage_num


def get_facilitator_review_queue(session_id: int | None = None) -> list[dict[str, Any]]:
    """
    Mengambil antrean jawaban isian singkat (short_text) yang berstatus NEEDS_REVIEW.
    Fasilitator dapat memeriksa jawaban peserta terhadap accepted_answers.
    """
    stmt = (
        db.select(Answer)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(NetworkingSubmission, Submission.id == NetworkingSubmission.submission_id)
        .join(Question, Answer.question_id == Question.id)
        .join(Team, Submission.team_id == Team.id)
        .options(
            joinedload(Answer.question),
            joinedload(Answer.submission).joinedload(Submission.team),
            joinedload(Answer.submission).joinedload(Submission.networking_submission),
        )
        .where(Answer.review_status == "NEEDS_REVIEW")
    )
    if session_id:
        stmt = stmt.where(Submission.session_id == session_id)

    answers = db.session.scalars(stmt).unique().all()
    queue = []
    for ans in answers:
        q = ans.question
        t = ans.submission.team
        queue.append({
            "answer_id": ans.id,
            "submission_id": ans.submission_id,
            "team_id": t.id,
            "team_code": t.team_code,
            "team_name": t.team_name,
            "school": t.school,
            "question_id": q.id,
            "order_number": q.order_number,
            "case_study": q.case_study,
            "question_text": q.text,
            "participant_answer": ans.text_answer or ans.selected_answer or "-",
            "user_answer": ans.text_answer or ans.selected_answer or "-",
            "accepted_answers": q.accepted_answers or [],
            "weight": q.weight,
            "facilitator_notes": ans.facilitator_notes or "",
        })
    return queue


def review_answer_by_facilitator(
    answer_id: int,
    admin_id: int,
    action: str,  # "ACCEPT" or "REJECT"
    notes: str | None = None,
) -> tuple[bool, str | None]:
    """
    Fasilitator memutuskan penerimaan jawaban isian peserta (ACCEPT / REJECT).
    Mencatat alasan dan pembaruan poin.
    """
    ans = db.session.get(Answer, answer_id)
    if not ans:
        return False, "Jawaban tidak ditemukan."

    sub = ans.submission
    net_sub = sub.networking_submission
    if not net_sub:
        return False, "Submission networking tidak valid."

    if net_sub.verification_status == "FINALIZED":
        return False, "Hasil sudah difinalisasi dan terkunci."

    old_status = ans.review_status
    old_correct = ans.is_correct
    old_points = ans.points_awarded

    if action.upper() == "ACCEPT":
        ans.is_correct = True
        ans.points_awarded = float(ans.question.weight)
        ans.review_status = "VERIFIED"
    elif action.upper() == "REJECT":
        ans.is_correct = False
        ans.points_awarded = 0.0
        ans.review_status = "REJECTED"
    else:
        return False, "Aksi tidak valid (harus ACCEPT atau REJECT)."

    ans.facilitator_notes = notes

    # Recalculate Stage 3 score & correct count
    net_sub.stage_3_score = calculate_stage_score(net_sub, 3)
    questions_s3 = get_stage_questions(sub.session, 3)
    q3_ids = {q.id for q in questions_s3}
    ans_s3 = db.session.scalars(
        db.select(Answer).where(
            Answer.submission_id == sub.id,
            Answer.question_id.in_(q3_ids),
        )
    ).all()
    correct_count = sum(1 for a in ans_s3 if a.is_correct)
    net_sub.stage_3_correct_count = correct_count
    net_sub.has_stamp = (correct_count >= 4)
    net_sub.provisional_score = round(
        net_sub.stage_1_score + net_sub.stage_2_score + net_sub.stage_3_score, 2
    )

    # Catat audit log
    audit = NetworkingSubmissionAudit(
        networking_submission_id=net_sub.id,
        admin_id=admin_id,
        action=f"REVIEW_ANSWER_{action.upper()}",
        old_values={"review_status": old_status, "is_correct": old_correct, "points": old_points},
        new_values={"review_status": ans.review_status, "is_correct": ans.is_correct, "points": ans.points_awarded},
        reason=notes or f"Verifikasi fasilitator untuk soal nomor {ans.question.order_number}",
    )
    db.session.add(audit)
    db.session.commit()
    return True, None


def finalize_networking_submission(
    networking_submission_id: int,
    admin_id: int,
    reason: str = "Finalisasi hasil Pos Networking",
    time_bonus: float | None = None,
    penalty: float = 0.0,
    notes: str | None = None,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """
    Finalisasi hasil pengerjaan Pos Networking oleh fasilitator.
    Idempoten: jika dijalankan berulang, tidak menggandakan skor.
    Menerapkan ketentuan Stamp:
    - Stamp diperoleh jika jawaban benar Tahap 3 >= 4 dari 5 soal.
    - Status Stamp terpisah dari skor total.
    - Hasil final dikirim ke tabel Score untuk leaderboard.
    """
    net_sub = db.session.get(NetworkingSubmission, networking_submission_id)
    if not net_sub:
        return False, "Data submission networking tidak ditemukan.", None

    if net_sub.verification_status == "FINALIZED":
        return True, None, {"final_score": net_sub.final_score, "has_stamp": net_sub.has_stamp}
    if net_sub.current_stage != 4:
        return False, "Tim belum menyelesaikan tiga tahap.", None

    if notes and not net_sub.facilitator_notes:
        net_sub.facilitator_notes = notes

    sub = net_sub.submission
    now = utcnow()

    # Recalculate all stage scores
    net_sub.stage_1_score = calculate_stage_score(net_sub, 1)
    net_sub.stage_2_score = calculate_stage_score(net_sub, 2)
    net_sub.stage_3_score = calculate_stage_score(net_sub, 3)

    # Recount correct answers for Stage 3
    questions_s3 = get_stage_questions(sub.session, 3)
    q3_ids = {q.id for q in questions_s3}
    ans_s3 = db.session.scalars(
        db.select(Answer).where(
            Answer.submission_id == sub.id,
            Answer.question_id.in_(q3_ids),
        )
    ).all()
    correct_count = sum(1 for a in ans_s3 if a.is_correct)
    net_sub.stage_3_correct_count = correct_count
    net_sub.has_stamp = (correct_count >= 4)

    raw_total = round(net_sub.stage_1_score + net_sub.stage_2_score + net_sub.stage_3_score, 2)
    # Bonus was frozen at quiz submission, independent of facilitator review time.
    net_sub.time_bonus = round(net_sub.time_bonus or 0.0, 2)
    net_sub.penalty = round(float(penalty), 2)
    final_score = round(raw_total + net_sub.time_bonus - net_sub.penalty, 2)

    old_status = net_sub.verification_status
    net_sub.final_score = final_score
    net_sub.provisional_score = raw_total
    net_sub.verification_status = "FINALIZED"
    net_sub.verified_by_admin_id = admin_id
    net_sub.verified_at = now
    net_sub.facilitator_notes = notes or reason

    sub.status = SubmissionStatus.GRADED

    # Upsert Score object
    score_obj = db.session.scalar(
        db.select(Score).where(Score.submission_id == sub.id)
    )
    if score_obj:
        score_obj.raw_score = raw_total
        score_obj.time_bonus = net_sub.time_bonus
        score_obj.final_score = final_score
        score_obj.submitted_at = sub.submitted_at
    else:
        score_obj = Score(
            submission_id=sub.id,
            raw_score=raw_total,
            time_bonus=net_sub.time_bonus,
            final_score=final_score,
            submitted_at=sub.submitted_at,
        )
        db.session.add(score_obj)

    # Audit log
    audit = NetworkingSubmissionAudit(
        networking_submission_id=net_sub.id,
        admin_id=admin_id,
        action="FINALIZE_RESULT",
        old_values={"verification_status": old_status},
        new_values={
            "verification_status": "FINALIZED",
            "raw_score": raw_total,
            "final_score": final_score,
            "has_stamp": net_sub.has_stamp,
            "stage_3_correct_count": net_sub.stage_3_correct_count,
        },
        reason=reason or "Finalisasi skor dan Stamp Pos Networking",
    )
    db.session.add(audit)
    db.session.commit()

    return True, None, {
        "raw_score": raw_total,
        "stage_1_score": net_sub.stage_1_score,
        "stage_2_score": net_sub.stage_2_score,
        "stage_3_score": net_sub.stage_3_score,
        "time_bonus": net_sub.time_bonus,
        "final_score": final_score,
        "stage_3_correct_count": net_sub.stage_3_correct_count,
        "has_stamp": net_sub.has_stamp,
    }


def facilitator_control_action(
    session_id: int,
    action: str,
    admin_id: int,
    reason: str,
    team_id: int | None = None,
    extra_seconds: int = 0,
    stage_num: int = 1,
) -> tuple[bool, str | None]:
    """
    Aksi kontrol panitia Pos Networking:
    - START_SESSION: Memulai sesi untuk seluruh tim.
    - ADD_TIME: Menambah waktu pengerjaan tahap dengan alasan wajib.
    - FORCE_SUBMIT: Memaksa pengumpulan pengerjaan dengan alasan wajib.
    - ALLOW_RECONNECT: Mengizinkan peserta masuk kembali (reset session_token) dengan alasan wajib.
    Seluruh tindakan sensitif dicatat dalam audit log dan bersifat idempoten.
    """
    if not reason or len(reason.strip()) < 3:
        return False, "Alasan tindakan wajib diisi (minimal 3 karakter)."

    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        return False, "Sesi kompetisi tidak ditemukan."

    now = utcnow()

    if session_obj.station.name.lower() != "networking":
        return False, "Sesi bukan Pos Networking."
    if stage_num not in (1, 2, 3):
        return False, "Tahap harus 1, 2, atau 3."
    if action == "START_SESSION":
        if session_obj.status == SessionStatus.RUNNING:
            return True, "Sesi sudah berjalan."

        if session_obj.status != SessionStatus.WAITING:
            return False, "Sesi sudah selesai atau dibatalkan."
        session_obj.status = SessionStatus.RUNNING
        session_obj.started_at = now
        if session_obj.question_set:
            session_obj.question_set.status = QuestionSetStatus.LOCKED

        # Ambil seluruh tim aktif di kelompok sesi
        teams = db.session.scalars(
            db.select(Team).where(Team.group_id == session_obj.group_id, Team.is_active.is_(True))
        ).all()

        for t in teams:
            sub, net_sub, _ = get_or_create_networking_submission(session_obj.id, t.id)
            if not net_sub.stage_1_started_at:
                net_sub.stage_1_started_at = now
            net_sub.verification_status = "IN_PROGRESS"

        db.session.commit()
        return True, "Sesi Pos Networking berhasil dimulai!"

    elif action == "ADD_TIME":
        if extra_seconds <= 0:
            return False, "Jumlah tambahan waktu harus lebih besar dari 0 detik."

        # Terapkan ke submission tim atau seluruh tim
        subs_query = db.select(NetworkingSubmission).join(Submission).where(
            Submission.session_id == session_id
        )
        if team_id:
            subs_query = subs_query.where(Submission.team_id == team_id)

        net_subs = db.session.scalars(subs_query).all()
        for ns in net_subs:
            old_dur = getattr(ns, f"stage_{stage_num}_duration_seconds", 300)
            setattr(ns, f"stage_{stage_num}_duration_seconds", old_dur + extra_seconds)

            audit = NetworkingSubmissionAudit(
                networking_submission_id=ns.id,
                admin_id=admin_id,
                action=f"ADD_TIME_STAGE_{stage_num}",
                old_values={"duration": old_dur},
                new_values={"duration": old_dur + extra_seconds, "added_seconds": extra_seconds},
                reason=reason,
            )
            db.session.add(audit)

        db.session.commit()
        return True, f"Tambahan {extra_seconds} detik berhasil ditambahkan pada Tahap {stage_num}."

    elif action == "FORCE_SUBMIT":
        subs_query = db.select(NetworkingSubmission).join(Submission).where(
            Submission.session_id == session_id
        )
        if team_id:
            subs_query = subs_query.where(Submission.team_id == team_id)

        net_subs = db.session.scalars(subs_query).all()
        for ns in net_subs:
            curr_st = ns.current_stage
            if curr_st in (1, 2, 3):
                submit_stage(ns.submission_id, curr_st, is_timeout=True)

            audit = NetworkingSubmissionAudit(
                networking_submission_id=ns.id,
                admin_id=admin_id,
                action="FORCE_SUBMIT",
                old_values={"current_stage": curr_st},
                new_values={"current_stage": ns.current_stage, "verification_status": ns.verification_status},
                reason=reason,
            )
            db.session.add(audit)

        db.session.commit()
        return True, "Pengerjaan berhasil dikumpulkan paksa oleh panitia."

    elif action == "ALLOW_RECONNECT":
        if not team_id:
            return False, "Tim wajib dipilih untuk izin masuk kembali."

        sub = db.session.scalar(
            db.select(Submission).where(
                Submission.session_id == session_id,
                Submission.team_id == team_id,
            )
        )
        if not sub or not sub.networking_submission:
            return False, "Submission tim tidak ditemukan."

        ns = sub.networking_submission
        old_token = ns.session_token
        ns.session_token = None  # Reset token agar device lain / tab baru bisa masuk

        audit = NetworkingSubmissionAudit(
            networking_submission_id=ns.id,
            admin_id=admin_id,
            action="ALLOW_RECONNECT",
            old_values={"session_token": old_token},
            new_values={"session_token": None},
            reason=reason,
        )
        db.session.add(audit)
        db.session.commit()
        return True, f"Izin masuk kembali diberikan untuk tim {sub.team.team_name}."

    return False, "Aksi kontrol tidak dikenal."
