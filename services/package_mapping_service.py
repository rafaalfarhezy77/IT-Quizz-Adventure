"""
Package Mapping Service for Mythic 3.0.
Handles assignment of Challenge Packages to Groups (A-D) using SAME_FOR_ALL and BY_GROUP strategies.
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


def get_group_mappings_for_station(station_id: int, session_id: int | None = None) -> dict[str, GroupPackageMapping | None]:
    """
    Mengambil pemetaan kelompok untuk suatu pos.
    Mengembalikan dict dalam format: {'A': mapping_obj, 'B': mapping_obj, 'C': mapping_obj, 'D': mapping_obj}
    """
    groups = db.session.scalars(db.select(Group).order_by(Group.code.asc())).all()
    result: dict[str, GroupPackageMapping | None] = {}

    for grp in groups:
        # Cari mapping per sesi jika session_id diberikan
        mapping = None
        if session_id:
            mapping = db.session.scalar(
                db.select(GroupPackageMapping).where(
                    GroupPackageMapping.station_id == station_id,
                    GroupPackageMapping.group_id == grp.id,
                    GroupPackageMapping.session_id == session_id,
                )
            )

        # Jika belum ada mapping per sesi, cari mapping default pos untuk kelompok ini
        if not mapping:
            mapping = db.session.scalar(
                db.select(GroupPackageMapping).where(
                    GroupPackageMapping.station_id == station_id,
                    GroupPackageMapping.group_id == grp.id,
                    GroupPackageMapping.session_id.is_(None),
                )
            )

        result[grp.code] = mapping

    return result


def apply_same_for_all_mapping(station_id: int, package_id: int, session_id: int | None = None) -> tuple[bool, str]:
    """
    Menerapkan strategi SAME_FOR_ALL:
    Seluruh Kelompok (A, B, C, D) ditugaskan ke paket yang sama.
    """
    station = db.session.get(Station, station_id)
    if not station:
        return False, "Pos tidak ditemukan."

    package = db.session.get(ChallengePackage, package_id)
    if not package:
        return False, "Paket soal tidak ditemukan."

    if package.station_id != station_id:
        return False, f"Paket '{package.package_code}' bukan milik pos '{station.name}'."

    if package.status not in (PackageStatus.ACTIVE, PackageStatus.LOCKED):
        return False, f"Paket harus berstatus ACTIVE atau LOCKED (status saat ini: {package.status.value})."

    groups = db.session.scalars(db.select(Group)).all()
    for grp in groups:
        # Upsert mapping
        existing = db.session.scalar(
            db.select(GroupPackageMapping).where(
                GroupPackageMapping.station_id == station_id,
                GroupPackageMapping.group_id == grp.id,
                GroupPackageMapping.session_id == session_id if session_id else GroupPackageMapping.session_id.is_(None),
            )
        )
        if existing:
            existing.package_id = package.id
            existing.strategy = "SAME_FOR_ALL"
        else:
            mapping = GroupPackageMapping(
                station_id=station_id,
                group_id=grp.id,
                package_id=package.id,
                session_id=session_id,
                strategy="SAME_FOR_ALL",
            )
            db.session.add(mapping)

    db.session.commit()
    return True, f"Berhasil memetakan paket '{package.package_code}' ke seluruh kelompok (SAME_FOR_ALL)."


def apply_by_group_mapping(
    station_id: int,
    group_package_dict: dict[str, int],
    session_id: int | None = None,
) -> tuple[bool, str]:
    """
    Menerapkan strategi BY_GROUP:
    Memasangkan masing-masing Kelompok (A, B, C, D) dengan paket spesifik.
    group_package_dict format: {'A': package_id_A, 'B': package_id_B, ...}
    """
    station = db.session.get(Station, station_id)
    if not station:
        return False, "Pos tidak ditemukan."

    for group_code, pkg_id in group_package_dict.items():
        if not pkg_id:
            continue

        grp = db.session.scalar(db.select(Group).where(Group.code == group_code.upper()))
        if not grp:
            continue

        package = db.session.get(ChallengePackage, pkg_id)
        if not package:
            return False, f"Paket ID {pkg_id} untuk Kelompok {group_code} tidak ditemukan."

        if package.station_id != station_id:
            return False, f"Paket '{package.package_code}' bukan milik pos '{station.name}'."

        if package.status not in (PackageStatus.ACTIVE, PackageStatus.LOCKED):
            return False, f"Paket '{package.package_code}' harus berstatus ACTIVE atau LOCKED (status: {package.status.value})."

        existing = db.session.scalar(
            db.select(GroupPackageMapping).where(
                GroupPackageMapping.station_id == station_id,
                GroupPackageMapping.group_id == grp.id,
                GroupPackageMapping.session_id == session_id if session_id else GroupPackageMapping.session_id.is_(None),
            )
        )
        if existing:
            existing.package_id = package.id
            existing.strategy = "BY_GROUP"
        else:
            mapping = GroupPackageMapping(
                station_id=station_id,
                group_id=grp.id,
                package_id=package.id,
                session_id=session_id,
                strategy="BY_GROUP",
            )
            db.session.add(mapping)

    db.session.commit()
    return True, "Pemetaan paket per kelompok (BY_GROUP) berhasil disimpan."


def save_package_mapping(
    station_id: int,
    strategy: str,
    same_package_id: int | None = None,
    group_package_map: dict | None = None,
    session_id: int | None = None,
) -> list[GroupPackageMapping]:
    """Helper untuk menyimpan pemetaan paket berdasarkan strategi."""
    if strategy in ("SAME_FOR_ALL", "same_for_all"):
        if not same_package_id:
            raise ValueError("Paket untuk SAME_FOR_ALL wajib ditentukan.")
        ok, msg = apply_same_for_all_mapping(station_id, same_package_id, session_id)
        if not ok:
            raise ValueError(msg)
    elif strategy in ("BY_GROUP", "by_group"):
        cleaned_map = {}
        for k, v in (group_package_map or {}).items():
            if isinstance(k, int):
                grp = db.session.get(Group, k)
                if grp:
                    cleaned_map[grp.code] = v
            else:
                cleaned_map[str(k)] = v
        ok, msg = apply_by_group_mapping(station_id, cleaned_map, session_id)
        if not ok:
            raise ValueError(msg)
    else:
        raise ValueError(f"Strategi '{strategy}' tidak didukung.")

    stmt = db.select(GroupPackageMapping).where(GroupPackageMapping.station_id == station_id)
    if session_id:
        stmt = stmt.where(GroupPackageMapping.session_id == session_id)
    else:
        stmt = stmt.where(GroupPackageMapping.session_id.is_(None))
    return db.session.scalars(stmt).all()



def get_assigned_package_for_group(
    station_id: int,
    group_id: int,
    session_id: int | None = None,
) -> ChallengePackage | None:
    """
    Mengambil paket aktif yang ditugaskan kepada kelompok tertentu pada pos dan sesi tertentu.
    Prioritas:
    1. Sesi terkait langsung memiliki package_id.
    2. Pemetaan per session_id.
    3. Pemetaan default pos untuk kelompok tersebut.
    """
    # 1. Cek langsung di session jika session_id tersedia
    if session_id:
        sess = db.session.get(CompetitionSession, session_id)
        if sess and sess.package_id:
            pkg = db.session.get(ChallengePackage, sess.package_id)
            if pkg:
                return pkg

        # 2. Cek mapping spesifik session
        mapping = db.session.scalar(
            db.select(GroupPackageMapping).where(
                GroupPackageMapping.station_id == station_id,
                GroupPackageMapping.group_id == group_id,
                GroupPackageMapping.session_id == session_id,
            )
        )
        if mapping and mapping.package:
            return mapping.package

    # 3. Cek mapping default pos
    default_mapping = db.session.scalar(
        db.select(GroupPackageMapping).where(
            GroupPackageMapping.station_id == station_id,
            GroupPackageMapping.group_id == group_id,
            GroupPackageMapping.session_id.is_(None),
        )
    )
    if default_mapping and default_mapping.package:
        return default_mapping.package

    return None


def validate_session_mapping_ready(station_id: int, group_id: int, session_id: int | None = None) -> tuple[bool, str | None, ChallengePackage | None]:
    """
    Validasi mutlak sebelum sesi dimulai:
    Sesi TIDAK BOLEH DIMULAI jika kelompok belum memiliki paket yang ditugaskan.
    Paket harus berstatus ACTIVE atau LOCKED.
    """
    pkg = get_assigned_package_for_group(station_id, group_id, session_id)
    if not pkg:
        station = db.session.get(Station, station_id)
        group = db.session.get(Group, group_id)
        st_name = station.name if station else f"ID {station_id}"
        grp_code = group.code if group else f"ID {group_id}"
        return False, f"Sesi tidak dapat dimulai: Kelompok {grp_code} belum memiliki Paket Soal/Studi Kasus pada Pos {st_name}.", None

    if pkg.status not in (PackageStatus.ACTIVE, PackageStatus.LOCKED):
        return False, f"Paket '{pkg.package_code}' yang ditugaskan berstatus {pkg.status.value}. Paket harus diaktifkan terlebih dahulu.", None

    return True, None, pkg


def make_package_snapshot(package: ChallengePackage) -> dict[str, Any]:
    """
    Menyimpan snapshot judul, studi kasus, ketentuan, dan konfigurasi penilaian
    saat submission dibuat agar riwayat hasil tidak berubah ketika paket diperbarui di kemudian hari.
    """
    return {
        "package_id": package.id,
        "package_code": package.package_code,
        "title": package.title,
        "description": package.description,
        "instructions": package.instructions,
        "challenge_type": package.challenge_type,
        "external_tool_url": package.external_tool_url,
        "rules_config": dict(package.rules_config or {}),
        "scoring_config": dict(package.scoring_config or {}),
        "duration_minutes": package.duration_minutes,
    }
