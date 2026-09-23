from datetime import datetime, timedelta, timezone
from sqlalchemy import update
from models import (
    CompetitionSession,
    Group,
    QuestionSet,
    QuestionSetStatus,
    SessionStatus,
    Station,
    db,
)


def get_server_now() -> datetime:
    """Return current server time as naive UTC to ensure SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_naive_utc(dt: datetime | None) -> datetime | None:
    """Ensure datetime object is naive UTC without timezone offset conflicts."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def get_remaining_seconds(session_obj: CompetitionSession, current_time: datetime | None = None) -> int:
    """
    Calculate remaining competition seconds based on official server time.
    Source of truth: started_at and duration_seconds stored in database.
    """
    if session_obj.status == SessionStatus.WAITING:
        return session_obj.duration_seconds

    if session_obj.status in (SessionStatus.FINISHED, SessionStatus.CANCELLED):
        return 0

    if session_obj.status == SessionStatus.RUNNING:
        if not session_obj.started_at:
            return session_obj.duration_seconds

        now = current_time or get_server_now()
        started = ensure_naive_utc(session_obj.started_at)
        elapsed = (now - started).total_seconds()
        remaining = int(session_obj.duration_seconds - elapsed)
        return max(0, remaining)

    return 0


def get_effective_status(session_obj: CompetitionSession, current_time: datetime | None = None) -> SessionStatus:
    """
    Determine the effective status of a session.
    If status is RUNNING but elapsed time >= duration, effectively returns FINISHED.
    Read-only calculation to prevent SQLite write-contention during high-concurrency polling.
    """
    if session_obj.status == SessionStatus.RUNNING:
        remaining = get_remaining_seconds(session_obj, current_time)
        if remaining <= 0:
            return SessionStatus.FINISHED
    return session_obj.status


def find_participant_session(station_id: int, group_id: int) -> CompetitionSession | None:
    """
    Find active or most relevant session for a participant's station and group.
    Priority:
    1. Active RUNNING session with remaining time > 0
    2. WAITING session
    3. Recently FINISHED session
    """
    sessions = (
        db.session.scalars(
            db.select(CompetitionSession)
            .where(
                CompetitionSession.station_id == station_id,
                CompetitionSession.group_id == group_id,
            )
            .order_by(CompetitionSession.created_at.desc())
        )
        .all()
    )

    if not sessions:
        return None

    # Check for active RUNNING first
    for s in sessions:
        if s.status == SessionStatus.RUNNING:
            return s

    # Check for WAITING next
    for s in sessions:
        if s.status == SessionStatus.WAITING:
            return s

    # Otherwise return latest session (e.g. FINISHED or CANCELLED)
    return sessions[0]


def create_session(
    station_id: int,
    group_id: int,
    question_set_id: int | None = None,
    duration_minutes: int = 30,
    package_id: int | None = None,
) -> CompetitionSession:
    """
    Create a new competition session in WAITING status with comprehensive validations.
    """
    station = db.session.get(Station, station_id)
    if not station or not station.is_active:
        raise ValueError("Pos perlombaan tidak ditemukan atau sedang tidak aktif.")

    group = db.session.get(Group, group_id)
    if not group:
        raise ValueError("Kelompok peserta tidak ditemukan.")

    if station.name.lower() == "networking":
        raise ValueError("Pos Networking memakai lobby khusus. Siapkan rotasi, kelompok, dan set soal di Konsol Pos Networking.")
    if station.name.lower() != "hardware" and not question_set_id:
        raise ValueError("Pilih bank soal READY untuk pos kuis ini.")

    qs = None
    if question_set_id:
        qs = db.session.get(QuestionSet, question_set_id)
        if not qs:
            raise ValueError("Bank soal tidak ditemukan.")

        if qs.station_id != station.id:
            raise ValueError(f"Bank soal '{qs.code}' bukan milik pos '{station.name}'.")

        if qs.status != QuestionSetStatus.READY:
            raise ValueError(
                f"Bank soal harus berstatus READY untuk dapat digunakan dalam sesi (status saat ini: {qs.status.value})."
            )

    if duration_minutes <= 0:
        raise ValueError("Durasi sesi harus lebih dari 0 menit.")

    # Duplicate check: check if WAITING or RUNNING session already exists for this station + group
    duplicate = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.station_id == station.id,
            CompetitionSession.group_id == group.id,
            CompetitionSession.status.in_([SessionStatus.WAITING, SessionStatus.RUNNING]),
        )
    )
    if duplicate:
        raise ValueError(
            f"Sudah ada sesi berstatus {duplicate.status.value} (ID: #{duplicate.id}) untuk Pos {station.name} dan Kelompok {group.code}."
        )

    # Deteksi paket jika tidak dispesifikasikan
    from services.package_mapping_service import get_assigned_package_for_group
    if not package_id:
        pkg = get_assigned_package_for_group(station.id, group.id)
        if pkg:
            package_id = pkg.id

    if not qs and not package_id:
        # Jika bukan station quiz atau ada paket untuk station ini, harus ada pemetaan paket
        pkg = get_assigned_package_for_group(station.id, group.id)
        if pkg:
            package_id = pkg.id

    duration_seconds = int(duration_minutes * 60)
    new_session = CompetitionSession(
        station_id=station.id,
        group_id=group.id,
        question_set_id=qs.id if qs else None,
        package_id=package_id,
        duration_seconds=duration_seconds,
        status=SessionStatus.WAITING,
    )
    db.session.add(new_session)
    db.session.commit()
    return new_session


def update_session(
    session_obj: CompetitionSession,
    station_id: int,
    group_id: int,
    question_set_id: int | None,
    duration_minutes: int,
) -> CompetitionSession:
    """
    Update an existing WAITING session.
    """
    if session_obj.status != SessionStatus.WAITING:
        raise ValueError(f"Hanya sesi berstatus WAITING yang dapat diedit (status saat ini: {session_obj.status.value}).")

    station = db.session.get(Station, station_id)
    if not station or not station.is_active:
        raise ValueError("Pos perlombaan tidak ditemukan atau tidak aktif.")

    group = db.session.get(Group, group_id)
    if not group:
        raise ValueError("Kelompok peserta tidak ditemukan.")

    if station.name.lower() == "networking":
        raise ValueError("Ubah sesi Networking melalui Konsol Pos Networking.")
    if station.name.lower() != "hardware" and not question_set_id:
        raise ValueError("Pilih bank soal READY untuk pos kuis ini.")

    qs = db.session.get(QuestionSet, question_set_id) if question_set_id else None
    if question_set_id and not qs:
        raise ValueError("Bank soal tidak ditemukan.")

    if qs and qs.station_id != station.id:
        raise ValueError(f"Bank soal '{qs.code}' bukan milik pos '{station.name}'.")

    if qs and qs.status != QuestionSetStatus.READY:
        raise ValueError(
            f"Bank soal harus berstatus READY untuk dapat digunakan dalam sesi (status saat ini: {qs.status.value})."
        )

    if duration_minutes <= 0:
        raise ValueError("Durasi sesi harus lebih dari 0 menit.")

    # Duplicate check excluding self
    duplicate = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.station_id == station.id,
            CompetitionSession.group_id == group.id,
            CompetitionSession.status.in_([SessionStatus.WAITING, SessionStatus.RUNNING]),
            CompetitionSession.id != session_obj.id,
        )
    )
    if duplicate:
        raise ValueError(
            f"Sudah ada sesi berstatus {duplicate.status.value} (ID: #{duplicate.id}) untuk Pos {station.name} dan Kelompok {group.code}."
        )

    session_obj.station_id = station.id
    session_obj.group_id = group.id
    session_obj.question_set_id = qs.id if qs else None
    session_obj.duration_seconds = int(duration_minutes * 60)
    db.session.commit()
    return session_obj


def start_session(session_obj: CompetitionSession) -> tuple[bool, str]:
    """
    Start a WAITING session atomically:
    - sets status = RUNNING
    - records server started_at
    - locks QuestionSet
    Includes double-start protection.
    """
    # Double-start protection
    if session_obj.status == SessionStatus.RUNNING:
        return False, "Sesi sudah berjalan. Waktu mulai tidak diubah."

    if session_obj.status != SessionStatus.WAITING:
        return False, f"Sesi dengan status {session_obj.status.value} tidak dapat dimulai."

    # Check question set status
    if session_obj.question_set and session_obj.question_set.status != QuestionSetStatus.READY:
        return False, f"Bank soal harus berstatus READY (status saat ini: {session_obj.question_set.status.value})."

    # Check conflicting running session for same station + group
    conflicting = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.station_id == session_obj.station_id,
            CompetitionSession.group_id == session_obj.group_id,
            CompetitionSession.status == SessionStatus.RUNNING,
            CompetitionSession.id != session_obj.id,
        )
    )
    if conflicting:
        return False, f"Sudah ada sesi lain yang sedang berjalan (ID: #{conflicting.id}) untuk pos dan kelompok ini."

    now = get_server_now()

    # Validasi dan penguncian paket tantangan
    from services.package_mapping_service import get_assigned_package_for_group
    from models import PackageStatus, ChallengePackage

    package = session_obj.package or get_assigned_package_for_group(
        session_obj.station_id, session_obj.group_id, session_obj.id
    )
    has_packages = db.session.scalar(
        db.select(db.func.count())
        .select_from(ChallengePackage)
        .where(ChallengePackage.station_id == session_obj.station_id)
    ) or 0

    if package:
        if package.status not in (PackageStatus.ACTIVE, PackageStatus.LOCKED):
            return False, f"Paket '{package.package_code}' yang ditugaskan harus berstatus ACTIVE atau LOCKED (status: {package.status.value})."
        session_obj.package_id = package.id
        package.status = PackageStatus.LOCKED
    elif has_packages > 0 or session_obj.station.name.lower() == "hardware":
        return False, f"Sesi tidak dapat dimulai: Kelompok {session_obj.group.code} belum memiliki Paket Soal/Studi Kasus pada pos ini."

    # Conditional write makes two dashboard requests for the same session agree on one timer.
    claimed = db.session.execute(
        update(CompetitionSession)
        .where(CompetitionSession.id == session_obj.id, CompetitionSession.status == SessionStatus.WAITING)
        .values(status=SessionStatus.RUNNING, started_at=now)
    )
    if claimed.rowcount != 1:
        db.session.rollback()
        return False, "Sesi sudah dimulai dari perangkat lain. Muat ulang halaman untuk melihat waktu resmi."
    if session_obj.question_set:
        session_obj.question_set.status = QuestionSetStatus.LOCKED

    db.session.commit()
    return True, "Sesi perlombaan berhasil dimulai!"


def finish_session(session_obj: CompetitionSession) -> tuple[bool, str]:
    """
    Finish a RUNNING session:
    - sets status = FINISHED
    - records official ended_at
    Includes double-finish protection.
    """
    # Double-finish protection
    if session_obj.status == SessionStatus.FINISHED:
        return False, "Sesi sudah berstatus FINISHED."

    if session_obj.status != SessionStatus.RUNNING:
        return False, f"Hanya sesi berstatus RUNNING yang dapat diselesaikan (status saat ini: {session_obj.status.value})."

    now = get_server_now()
    started = ensure_naive_utc(session_obj.started_at)
    if started and (now - started).total_seconds() >= session_obj.duration_seconds:
        session_obj.ended_at = started + timedelta(seconds=session_obj.duration_seconds)
    else:
        session_obj.ended_at = now

    session_obj.status = SessionStatus.FINISHED
    db.session.commit()
    return True, "Sesi perlombaan berhasil diakhiri."


def cancel_session(session_obj: CompetitionSession) -> tuple[bool, str]:
    """
    Cancel a WAITING session:
    - sets status = CANCELLED
    """
    if session_obj.status != SessionStatus.WAITING:
        return False, f"Hanya sesi berstatus WAITING yang dapat dibatalkan (status saat ini: {session_obj.status.value})."

    session_obj.status = SessionStatus.CANCELLED
    db.session.commit()
    return True, "Sesi perlombaan berhasil dibatalkan."


def delete_session(session_obj: CompetitionSession) -> tuple[bool, str]:
    """
    Delete a session and its associated submissions, answers, and scores.
    RUNNING sessions cannot be deleted without finishing/cancelling first.
    """
    if session_obj.status == SessionStatus.RUNNING:
        return False, "Sesi yang sedang berjalan (RUNNING) tidak dapat dihapus. Silakan akhiri atau batalkan sesi terlebih dahulu."

    session_id = session_obj.id
    for sub in list(session_obj.submissions):
        if sub.score:
            db.session.delete(sub.score)
        for ans in list(sub.answers):
            db.session.delete(ans)
        db.session.delete(sub)

    db.session.delete(session_obj)
    db.session.commit()
    return True, f"Histori sesi #{session_id} dan seluruh data pengerjaannya berhasil dihapus."


def clear_session_history(only_finished: bool = True) -> tuple[int, str]:
    """
    Clear history of sessions.
    If only_finished is True, deletes FINISHED and CANCELLED sessions.
    Returns (count, message).
    """
    if only_finished:
        sessions = db.session.scalars(
            db.select(CompetitionSession).where(
                CompetitionSession.status.in_([SessionStatus.FINISHED, SessionStatus.CANCELLED])
            )
        ).all()
    else:
        sessions = db.session.scalars(
            db.select(CompetitionSession).where(
                CompetitionSession.status != SessionStatus.RUNNING
            )
        ).all()

    count = len(sessions)
    if count == 0:
        return 0, "Tidak ada histori sesi yang dapat dihapus."

    for s in sessions:
        for sub in list(s.submissions):
            if sub.score:
                db.session.delete(sub.score)
            for ans in list(sub.answers):
                db.session.delete(ans)
            db.session.delete(sub)
        db.session.delete(s)

    db.session.commit()
    return count, f"Berhasil menghapus {count} histori sesi beserta seluruh data nilainya."
