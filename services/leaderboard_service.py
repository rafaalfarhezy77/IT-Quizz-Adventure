import csv
import io
import re
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from models import (
    CompetitionSession,
    Group,
    Score,
    SessionStatus,
    Station,
    Submission,
    SubmissionStatus,
    Team,
    db,
)


def calculate_rankings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Menghitung peringkat kompetisi (Competition Ranking: 1, 2, 2, 4...)
    berdasarkan aturan tie-breaker deterministik:
    1. final_score DESC
    2. raw_score DESC
    3. time_bonus DESC
    4. submitted_at ASC (waktu lebih awal lebih tinggi)
    5. team_code ASC (stabilitas teknis)
    """
    def sort_key(x: dict[str, Any]):
        sub_time = x.get("submitted_at")
        if isinstance(sub_time, str):
            try:
                sub_time = datetime.fromisoformat(sub_time)
            except Exception:
                sub_time = datetime.max
        elif not isinstance(sub_time, datetime):
            sub_time = datetime.max

        return (
            -float(x.get("final_score") or 0.0),
            -float(x.get("raw_score") or 0.0),
            -float(x.get("time_bonus") or 0.0),
            sub_time,
            str(x.get("team_code") or ""),
        )

    sorted_items = sorted(items, key=sort_key)

    current_rank = 1
    for idx, item in enumerate(sorted_items):
        if idx > 0:
            prev = sorted_items[idx - 1]
            prev_time = prev.get("submitted_at")
            curr_time = item.get("submitted_at")

            # Jika skor akhir, raw score, time bonus, dan waktu submit persis sama -> tie rank
            is_exact_tie = (
                float(prev.get("final_score") or 0.0) == float(item.get("final_score") or 0.0)
                and float(prev.get("raw_score") or 0.0) == float(item.get("raw_score") or 0.0)
                and float(prev.get("time_bonus") or 0.0) == float(item.get("time_bonus") or 0.0)
                and prev_time == curr_time
            )
            if not is_exact_tie:
                current_rank = idx + 1
        item["rank"] = current_rank

    return sorted_items


def get_session_leaderboard(session_id: int) -> dict[str, Any]:
    """
    Mengambil data leaderboard peserta untuk satu sesi lomba tertentu.
    Hanya menampilkan hasil tim yang sudah difinalisasi (SUBMITTED / TIMED_OUT / GRADED).
    Tim yang masih mengerjakan atau belum mulai ditampilkan di bagian bawah tanpa skor sementara.
    """
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        return {"session": None, "ranked_rows": [], "uncompleted_rows": []}

    # Ambil seluruh submission untuk sesi ini
    submissions = db.session.scalars(
        db.select(Submission)
        .options(
            joinedload(Submission.team),
            joinedload(Submission.score),
            joinedload(Submission.session).joinedload(CompetitionSession.station),
            joinedload(Submission.session).joinedload(CompetitionSession.group),
        )
        .where(Submission.session_id == session_id)
    ).unique().all()

    # Seluruh tim yang terdaftar pada kelompok sesi ini
    all_teams = db.session.scalars(
        db.select(Team)
        .where(Team.group_id == session_obj.group_id, Team.is_active.is_(True))
        .order_by(Team.team_code.asc())
    ).all()

    submissions_by_team = {s.team_id: s for s in submissions}

    completed_data: list[dict[str, Any]] = []
    uncompleted_data: list[dict[str, Any]] = []

    for team in all_teams:
        sub = submissions_by_team.get(team.id)
        if sub and sub.status in (
            SubmissionStatus.SUBMITTED,
            SubmissionStatus.TIMED_OUT,
            SubmissionStatus.GRADED,
        ) and sub.score:
            score = sub.score
            completed_data.append({
                "submission_id": sub.id,
                "team_id": team.id,
                "team_code": team.team_code,
                "team_name": team.team_name,
                "school": team.school,
                "station_name": session_obj.station.name,
                "group_code": session_obj.group.code,
                "raw_score": score.raw_score,
                "time_bonus": score.time_bonus,
                "final_score": score.final_score,
                "status": sub.status.value,
                "submitted_at": score.submitted_at or sub.submitted_at,
            })
        else:
            status_label = "Mengerjakan Kuis" if sub and sub.status == SubmissionStatus.IN_PROGRESS else "Belum Mulai"
            uncompleted_data.append({
                "submission_id": sub.id if sub else None,
                "team_id": team.id,
                "team_code": team.team_code,
                "team_name": team.team_name,
                "school": team.school,
                "station_name": session_obj.station.name,
                "group_code": session_obj.group.code,
                "raw_score": None,
                "time_bonus": None,
                "final_score": None,
                "status": status_label,
                "submitted_at": None,
                "rank": "-",
            })

    ranked_completed = calculate_rankings(completed_data)

    return {
        "session": session_obj,
        "station": session_obj.station,
        "group": session_obj.group,
        "ranked_rows": ranked_completed,
        "uncompleted_rows": uncompleted_data,
        "total_teams": len(all_teams),
        "completed_count": len(ranked_completed),
    }


def get_filtered_results(
    station_id: int | None = None,
    group_id: int | None = None,
    session_id: int | None = None,
    status: str | None = None,
    search_query: str | None = None,
) -> list[dict[str, Any]]:
    """
    Mengambil seluruh hasil submission lomba untuk panel Admin dengan filter dinamis dan pencarian teks.
    """
    stmt = (
        db.select(Submission)
        .join(CompetitionSession, Submission.session_id == CompetitionSession.id)
        .join(Team, Submission.team_id == Team.id)
        .outerjoin(Score, Submission.id == Score.submission_id)
        .options(
            joinedload(Submission.team),
            joinedload(Submission.score),
            joinedload(Submission.session).joinedload(CompetitionSession.station),
            joinedload(Submission.session).joinedload(CompetitionSession.group),
        )
    )

    if station_id:
        stmt = stmt.where(CompetitionSession.station_id == station_id)
    if group_id:
        stmt = stmt.where(CompetitionSession.group_id == group_id)
    if session_id:
        stmt = stmt.where(CompetitionSession.id == session_id)
    if status:
        stmt = stmt.where(Submission.status == status)

    if search_query:
        q_clean = f"%{search_query.strip()}%"
        stmt = stmt.where(
            or_(
                Team.team_code.ilike(q_clean),
                Team.team_name.ilike(q_clean),
                Team.school.ilike(q_clean),
            )
        )

    submissions = db.session.scalars(stmt).unique().all()

    items: list[dict[str, Any]] = []
    for sub in submissions:
        score = sub.score
        items.append({
            "submission_id": sub.id,
            "session_id": sub.session_id,
            "team_id": sub.team_id,
            "team_code": sub.team.team_code,
            "team_name": sub.team.team_name,
            "school": sub.team.school,
            "station_id": sub.session.station_id,
            "station_name": sub.session.station.name,
            "group_id": sub.session.group_id,
            "group_code": sub.session.group.code,
            "raw_score": score.raw_score if score else 0.0,
            "time_bonus": score.time_bonus if score else 0.0,
            "final_score": score.final_score if score else 0.0,
            "status": sub.status.value,
            "started_at": sub.started_at,
            "submitted_at": (score.submitted_at if score else sub.submitted_at),
        })

    return calculate_rankings(items)


def get_session_monitoring_data(session_obj: CompetitionSession) -> dict[str, Any]:
    """
    Menghasilkan data pantauan progres pengerjaan seluruh tim pada satu sesi lomba.
    Status terdeteksi:
    - NOT_STARTED: Belum membuka kuis / belum ada row submission.
    - IN_PROGRESS: Sedang mengerjakan soal kuis.
    - SUBMITTED: Telah selesai dan mengirim jawaban.
    - TIMED_OUT: Waktu pengerjaan habis dan difinalisasi otomatis.
    """
    teams = db.session.scalars(
        db.select(Team)
        .where(Team.group_id == session_obj.group_id, Team.is_active.is_(True))
        .order_by(Team.team_code.asc())
    ).all()

    submissions = db.session.scalars(
        db.select(Submission)
        .options(joinedload(Submission.score))
        .where(Submission.session_id == session_obj.id)
    ).unique().all()

    sub_map = {s.team_id: s for s in submissions}

    team_rows: list[dict[str, Any]] = []
    not_started_cnt = 0
    in_progress_cnt = 0
    submitted_cnt = 0
    timed_out_cnt = 0
    waiting_for_host_cnt = 0

    for t in teams:
        sub = sub_map.get(t.id)
        if sub is None:
            if session_obj.status == SessionStatus.WAITING:
                st = "WAITING_FOR_HOST"
                waiting_for_host_cnt += 1
            else:
                st = "NOT_STARTED"
                not_started_cnt += 1
            raw_s = 0.0
            bonus_s = 0.0
            final_s = 0.0
            sub_id = None
            started_at = None
            submitted_at = None
        else:
            st = sub.status.value
            if sub.status == SubmissionStatus.IN_PROGRESS:
                in_progress_cnt += 1
            elif sub.status == SubmissionStatus.SUBMITTED:
                submitted_cnt += 1
            elif sub.status == SubmissionStatus.TIMED_OUT:
                timed_out_cnt += 1
            else:
                submitted_cnt += 1

            sub_id = sub.id
            started_at = sub.started_at
            submitted_at = sub.score.submitted_at if sub.score else sub.submitted_at
            raw_s = sub.score.raw_score if sub.score else 0.0
            bonus_s = sub.score.time_bonus if sub.score else 0.0
            final_s = sub.score.final_score if sub.score else 0.0

        team_rows.append({
            "team_id": t.id,
            "team_code": t.team_code,
            "team_name": t.team_name,
            "school": t.school,
            "submission_id": sub_id,
            "status": st,
            "started_at": started_at,
            "submitted_at": submitted_at,
            "raw_score": raw_s,
            "time_bonus": bonus_s,
            "final_score": final_s,
        })

    return {
        "session_id": session_obj.id,
        "station_name": session_obj.station.name,
        "group_code": session_obj.group.code,
        "teams": team_rows,
        "summary": {
            "total_teams": len(teams),
            "not_started": not_started_cnt,
            "waiting_for_host": waiting_for_host_cnt,
            "in_progress": in_progress_cnt,
            "submitted": submitted_cnt,
            "timed_out": timed_out_cnt,
        },
    }


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitasi sel CSV terhadap formula injection (CWE-1236).
    Jika string diawali dengan '=', '+', '-', atau '@', beri prefix tanda petik tunggal (').
    """
    if value is None:
        return ""
    str_val = str(value).strip()
    if str_val and str_val[0] in ("=", "+", "-", "@"):
        return f"'{str_val}"
    return str_val


def generate_results_csv(
    results: list[dict[str, Any]],
    station_name: str | None = None,
    group_code: str | None = None,
) -> tuple[str, str]:
    """
    Membentuk string CSV ber-BOM UTF-8 (utf-8-sig) dan nama berkas yang informatif dan aman.
    """
    # Buat nama berkas
    parts = ["it-quest-hasil"]
    if station_name:
        clean_st = re.sub(r"[^a-zA-Z0-9]+", "-", station_name.lower()).strip("-")
        parts.append(clean_st)
    if group_code:
        parts.append(f"kelompok-{group_code.lower()}")
    filename = f"{'-'.join(parts)}.csv"

    output = io.StringIO()
    # Tulis UTF-8 BOM agar terbaca sempurna di Microsoft Excel Windows
    output.write("\ufeff")

    fieldnames = [
        "rank",
        "team_code",
        "team_name",
        "school",
        "station",
        "group",
        "raw_score",
        "time_bonus",
        "final_score",
        "status",
        "submitted_at",
    ]

    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(fieldnames)

    for r in results:
        sub_time_str = ""
        if r.get("submitted_at"):
            if isinstance(r["submitted_at"], datetime):
                sub_time_str = r["submitted_at"].strftime("%Y-%m-%d %H:%M:%S")
            else:
                sub_time_str = str(r["submitted_at"])

        writer.writerow([
            r.get("rank", "-"),
            sanitize_csv_cell(r.get("team_code")),
            sanitize_csv_cell(r.get("team_name")),
            sanitize_csv_cell(r.get("school")),
            sanitize_csv_cell(r.get("station_name")),
            sanitize_csv_cell(r.get("group_code")),
            f"{float(r.get('raw_score') or 0.0):.2f}",
            f"{float(r.get('time_bonus') or 0.0):.2f}",
            f"{float(r.get('final_score') or 0.0):.2f}",
            r.get("status", ""),
            sub_time_str,
        ])

    return output.getvalue(), filename
