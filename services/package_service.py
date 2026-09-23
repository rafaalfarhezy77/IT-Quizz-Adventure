"""
Package Service for Mythic 3.0.
Manages Challenge Packages (Paket Soal / Studi Kasus) for all competition stations.
"""
from typing import Any
from models import (
    ChallengePackage,
    CompetitionSession,
    Group,
    GroupPackageMapping,
    PackageStatus,
    Station,
    Submission,
    db,
)


def get_packages_by_station(station_id: int | None = None, status: str | None = None) -> list[ChallengePackage]:
    """Mengambil daftar paket soal/studi kasus, dapat difilter berdasarkan pos dan status."""
    stmt = db.select(ChallengePackage)
    if station_id:
        stmt = stmt.where(ChallengePackage.station_id == station_id)
    if status and status != "all":
        try:
            status_enum = PackageStatus[status.upper()]
            stmt = stmt.where(ChallengePackage.status == status_enum)
        except KeyError:
            pass
    stmt = stmt.order_by(ChallengePackage.station_id.asc(), ChallengePackage.package_code.asc())
    return db.session.scalars(stmt).all()


def get_package_by_id(package_id: int) -> ChallengePackage | None:
    """Mengambil paket soal berdasarkan ID."""
    return db.session.get(ChallengePackage, package_id)


def is_package_used(package_id: int) -> bool:
    """
    Mengecek apakah paket sudah pernah digunakan dalam sesi lomba atau ada submission terkait.
    Paket yang sudah pernah digunakan dilarang dihapus permanen.
    """
    has_sessions = db.session.scalar(
        db.select(db.func.count())
        .select_from(CompetitionSession)
        .where(CompetitionSession.package_id == package_id)
    ) or 0
    if has_sessions > 0:
        return True

    has_submissions = db.session.scalar(
        db.select(db.func.count())
        .select_from(Submission)
        .where(Submission.package_id == package_id)
    ) or 0
    if has_submissions > 0:
        return True

    has_mappings = db.session.scalar(
        db.select(db.func.count())
        .select_from(GroupPackageMapping)
        .where(GroupPackageMapping.package_id == package_id)
    ) or 0
    return has_mappings > 0


def is_package_editable(package: ChallengePackage) -> tuple[bool, str | None]:
    """
    Mengecek apakah paket dapat diedit.
    Paket tidak boleh diedit setelah sesi terkait berjalan atau jika berstatus LOCKED.
    """
    if package.status == PackageStatus.LOCKED:
        return False, "Paket sedang terkunci (LOCKED) oleh sesi yang sedang berjalan. Duplikasi paket untuk membuat versi baru."

    # Cek apakah ada sesi aktif (RUNNING) yang menggunakan paket ini
    active_session = db.session.scalar(
        db.select(CompetitionSession).where(
            CompetitionSession.package_id == package.id,
            CompetitionSession.status.in_(["RUNNING", "WAITING"]),
        )
    )
    if active_session:
        return False, f"Paket terikat pada sesi #{active_session.id} ({active_session.status.value}). Duplikasi paket untuk membuat revisi."

    return True, None


def validate_scoring_weights(scoring_config: dict[str, Any] | None) -> tuple[bool, str | None]:
    """
    Memvalidasi bahwa total bobot penilaian sesuai dengan standar sistem (total = 100).
    """
    if not scoring_config:
        return False, "Konfigurasi penilaian belum diisi."

    weights_keys = [
        "weight_compatibility",
        "weight_budget",
        ("weight_cpu_target", "weight_cpu"),
        ("weight_gpu_target", "weight_gpu"),
        "weight_completeness",
        "weight_efficiency",
        "weight_time_bonus",
    ]

    total = 0.0
    for item in weights_keys:
        if isinstance(item, tuple):
            primary, alt = item
            val = scoring_config.get(primary)
            if val is None:
                val = scoring_config.get(alt, 0.0)
            key_name = primary
        else:
            val = scoring_config.get(item, 0.0)
            key_name = item

        try:
            val_f = float(val)
            if val_f < 0:
                return False, f"Bobot '{key_name}' tidak boleh bernilai negatif."
            total += val_f
        except (TypeError, ValueError):
            return False, f"Nilai bobot '{key_name}' harus berupa angka valid."

    # Toleransi floating point
    if round(total, 2) != 100.0:
        return False, f"Total bobot penilaian harus berjumlah 100% (saat ini: {round(total, 2)}%)."

    return True, None


def generate_next_package_code(station_id: int) -> str:
    """Menghasilkan nama/kode paket berikutnya untuk pos, misal 'Paket 01', 'Paket 02'."""
    existing_packages = db.session.scalars(
        db.select(ChallengePackage.package_code)
        .where(ChallengePackage.station_id == station_id)
    ).all()

    nums = []
    for code in existing_packages:
        cleaned = code.lower().replace("paket", "").strip()
        if cleaned.isdigit():
            nums.append(int(cleaned))

    next_num = max(nums) + 1 if nums else 1
    new_code = f"Paket {next_num:02d}"

    while new_code in existing_packages:
        next_num += 1
        new_code = f"Paket {next_num:02d}"

    return new_code


def create_package(
    station_id: int,
    package_code: str,
    title: str,
    description: str,
    instructions: str,
    challenge_type: str = "hardware_build_challenge",
    external_tool_url: str | None = None,
    rules_config: dict[str, Any] | None = None,
    scoring_config: dict[str, Any] | None = None,
    duration_minutes: int = 30,
    status: PackageStatus = PackageStatus.DRAFT,
    question_set_id: int | None = None,
) -> ChallengePackage:
    """Membuat paket tantangan baru."""
    station = db.session.get(Station, station_id)
    if not station:
        raise ValueError("Pos tidak ditemukan.")

    # Cek duplikat package_code pada station yang sama
    duplicate = db.session.scalar(
        db.select(ChallengePackage).where(
            ChallengePackage.station_id == station_id,
            ChallengePackage.package_code == package_code.strip(),
        )
    )
    if duplicate:
        raise ValueError(f"Kode paket '{package_code}' sudah digunakan pada pos ini.")

    if duration_minutes <= 0:
        raise ValueError("Durasi pengerjaan harus lebih dari 0 menit.")

    if status == PackageStatus.ACTIVE and challenge_type == "hardware_build_challenge":
        is_valid, err = validate_scoring_weights(scoring_config)
        if not is_valid:
            raise ValueError(f"Tidak dapat mengaktifkan paket: {err}")

    package = ChallengePackage(
        station_id=station_id,
        package_code=package_code.strip(),
        title=title.strip(),
        description=description.strip(),
        instructions=instructions.strip(),
        challenge_type=challenge_type,
        external_tool_url=external_tool_url.strip() if external_tool_url else None,
        rules_config=rules_config or {},
        scoring_config=scoring_config or {},
        duration_minutes=duration_minutes,
        status=status,
        question_set_id=question_set_id,
    )
    db.session.add(package)
    db.session.commit()
    return package


def update_package(
    package: ChallengePackage,
    package_code: str,
    title: str,
    description: str,
    instructions: str,
    external_tool_url: str | None = None,
    rules_config: dict[str, Any] | None = None,
    scoring_config: dict[str, Any] | None = None,
    duration_minutes: int = 30,
    status: PackageStatus | None = None,
) -> ChallengePackage:
    """Memperbarui paket tantangan."""
    editable, reason = is_package_editable(package)
    if not editable:
        raise ValueError(reason)

    cleaned_code = package_code.strip()
    if cleaned_code != package.package_code:
        duplicate = db.session.scalar(
            db.select(ChallengePackage).where(
                ChallengePackage.station_id == package.station_id,
                ChallengePackage.package_code == cleaned_code,
                ChallengePackage.id != package.id,
            )
        )
        if duplicate:
            raise ValueError(f"Kode paket '{cleaned_code}' sudah digunakan pada pos ini.")

    if status == PackageStatus.ACTIVE and package.challenge_type == "hardware_build_challenge":
        is_valid, err = validate_scoring_weights(scoring_config or package.scoring_config)
        if not is_valid:
            raise ValueError(f"Tidak dapat mengaktifkan paket: {err}")

    package.package_code = cleaned_code
    package.title = title.strip()
    package.description = description.strip()
    package.instructions = instructions.strip()
    if external_tool_url is not None:
        package.external_tool_url = external_tool_url.strip() or None
    if rules_config is not None:
        package.rules_config = rules_config
    if scoring_config is not None:
        package.scoring_config = scoring_config
    if duration_minutes > 0:
        package.duration_minutes = duration_minutes
    if status is not None:
        package.status = status

    db.session.commit()
    return package


def duplicate_package(package_id: int) -> ChallengePackage:
    """
    Menduplikasi paket yang sudah ada.
    Menghasilkan salinan paket dalam status DRAFT dengan kode paket baru yang unik.
    """
    original = db.session.get(ChallengePackage, package_id)
    if not original:
        raise ValueError("Paket asli tidak ditemukan.")

    next_code = generate_next_package_code(original.station_id)

    duplicated = ChallengePackage(
        station_id=original.station_id,
        package_code=next_code,
        title=f"{original.title} (Salinan)",
        description=original.description,
        instructions=original.instructions,
        challenge_type=original.challenge_type,
        external_tool_url=original.external_tool_url,
        rules_config=dict(original.rules_config or {}),
        scoring_config=dict(original.scoring_config or {}),
        duration_minutes=original.duration_minutes,
        status=PackageStatus.DRAFT,
        question_set_id=original.question_set_id,
    )
    db.session.add(duplicated)
    db.session.commit()
    return duplicated


def set_package_status(package_id: int, new_status: PackageStatus) -> tuple[bool, str]:
    """Mengubah status paket dengan validasi."""
    package = db.session.get(ChallengePackage, package_id)
    if not package:
        return False, "Paket tidak ditemukan."

    if new_status == PackageStatus.ACTIVE:
        if package.challenge_type == "hardware_build_challenge":
            is_valid, err = validate_scoring_weights(package.scoring_config)
            if not is_valid:
                return False, f"Gagal mengaktifkan paket: {err}"

    package.status = new_status
    db.session.commit()
    return True, f"Status paket '{package.package_code}' berhasil diubah menjadi {new_status.value}."


def delete_or_archive_package(package_id: int) -> tuple[bool, str]:
    """
    Menghapus paket jika belum pernah digunakan sama sekali.
    Jika sudah pernah digunakan dalam sesi, pemetaan, atau submission, hanya boleh diarsipkan.
    """
    package = db.session.get(ChallengePackage, package_id)
    if not package:
        return False, "Paket tidak ditemukan."

    if is_package_used(package_id):
        package.status = PackageStatus.ARCHIVED
        db.session.commit()
        return True, f"Paket '{package.package_code}' telah memiliki riwayat sesi/pengerjaan sehingga tidak dapat dihapus permanen. Status paket otomatis diubah menjadi ARCHIVED."

    code = package.package_code
    db.session.delete(package)
    db.session.commit()
    return True, f"Paket '{code}' berhasil dihapus permanen."


def archive_package(package_id: int) -> tuple[bool, str]:
    """Mengarsipkan paket (status ARCHIVED)."""
    return set_package_status(package_id, PackageStatus.ARCHIVED)


def delete_package(package_id: int) -> tuple[bool, str]:
    """Alias untuk delete_or_archive_package."""
    return delete_or_archive_package(package_id)

