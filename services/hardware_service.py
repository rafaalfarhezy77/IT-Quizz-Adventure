"""
Hardware Service for Mythic 3.0.
Handles Hardware Challenge submissions, draft autosave, secure screenshot uploads,
and committee verification workflow with complete audit logging.
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import current_app
from werkzeug.datastructures import FileStorage

from models import (
    Admin,
    CompetitionSession,
    HardwareSubmission,
    HardwareSubmissionAudit,
    Score,
    Submission,
    SubmissionStatus,
    Team,
    db,
)
from services.hardware_scoring_service import calculate_hardware_scores
from services.package_mapping_service import get_assigned_package_for_group, make_package_snapshot
from services.session_service import get_remaining_seconds, get_server_now

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_buildcores_url(url: str) -> tuple[bool, str | None]:
    """
    Validasi protokol (HTTP/HTTPS) dan domain BuildCores.
    Tidak rapuh terhadap variasi path URL BuildCores.
    """
    if not url or not isinstance(url, str):
        return False, "URL BuildCores wajib diisi."

    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False, "URL harus menggunakan protokol HTTP atau HTTPS."

        netloc = parsed.netloc.lower()
        if not ("buildcores.com" in netloc):
            return False, "URL harus berasal dari situs resmi BuildCores (buildcores.com)."

        return True, None
    except Exception:
        return False, "Format URL BuildCores tidak valid."


def validate_and_save_screenshot(file_storage: FileStorage) -> tuple[bool, str | None, str | None]:
    """
    Validasi berkas upload tangkapan layar BuildCores:
    - Format hanya PNG, JPG/JPEG, dan WebP.
    - Ukuran berkas maksimal 5 MB.
    - Nama berkas acak aman (UUID) untuk mencegah path traversal dan benturan nama.
    - Validasi tipe file/magic bytes pada server untuk mencegah unggahan executable.
    Mengembalikan (success, filename_or_path, error_message)
    """
    if not file_storage or not file_storage.filename:
        return False, None, "Berkas tangkapan layar wajib diunggah."

    original_filename = file_storage.filename.strip()
    ext = os.path.splitext(original_filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return False, None, f"Format berkas tidak diizinkan. Hanya menerima berkas gambar {', '.join(sorted(ALLOWED_EXTENSIONS))}."

    # Periksa ukuran berkas (baca chunk pertama dan seek)
    file_storage.seek(0, os.SEEK_END)
    file_size = file_storage.tell()
    file_storage.seek(0)

    if file_size > MAX_FILE_SIZE:
        return False, None, f"Ukuran berkas terlalu besar ({file_size / (1024 * 1024):.1f} MB). Maksimal 5 MB."

    if file_size == 0:
        return False, None, "Berkas yang diunggah kosong."

    # Pemeriksaan Magic Bytes di sisi server
    header = file_storage.read(32)
    file_storage.seek(0)

    is_valid_image = False
    # PNG: \x89PNG\r\n\x1a\n
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        is_valid_image = True
    # JPEG: \xff\xd8\xff
    elif header.startswith(b"\xff\xd8\xff"):
        is_valid_image = True
    # WebP: RIFF....WEBP
    elif header.startswith(b"RIFF") and b"WEBP" in header[:16]:
        is_valid_image = True

    if not is_valid_image:
        return False, None, "Konten berkas bukan gambar yang valid atau terindikasi berkas executable/berbahaya."

    # Nama file acak dan aman
    safe_filename = f"{uuid.uuid4().hex}{ext}"

    # Pastikan direktori tujuan tersedia
    upload_base = current_app.config.get("UPLOAD_FOLDER", Path(current_app.instance_path) / "uploads")
    hardware_dir = Path(upload_base) / "hardware"
    hardware_dir.mkdir(parents=True, exist_ok=True)

    dest_path = hardware_dir / safe_filename
    file_storage.save(str(dest_path))

    return True, safe_filename, None


def get_or_create_hardware_submission(session_id: int, team_id: int) -> tuple[Submission, HardwareSubmission]:
    """
    Mengambil atau membuat Submission inti dan HardwareSubmission terkait.
    """
    session_obj = db.session.get(CompetitionSession, session_id)
    if not session_obj:
        raise ValueError("Sesi lomba tidak ditemukan.")

    team = db.session.get(Team, team_id)
    if not team:
        raise ValueError("Tim tidak ditemukan.")

    submission = db.session.scalar(
        db.select(Submission).where(
            Submission.session_id == session_id,
            Submission.team_id == team_id,
        )
    )

    package = session_obj.package or get_assigned_package_for_group(
        session_obj.station_id, session_obj.group_id, session_obj.id
    )

    if not submission:
        now = get_server_now()
        submission = Submission(
            session_id=session_id,
            team_id=team_id,
            package_id=package.id if package else None,
            package_snapshot=make_package_snapshot(package) if package else None,
            submission_type="hardware_build_challenge",
            status=SubmissionStatus.IN_PROGRESS,
            started_at=now,
        )
        db.session.add(submission)
        db.session.flush()

    hw_sub = submission.hardware_submission
    if not hw_sub:
        hw_sub = HardwareSubmission(
            submission_id=submission.id,
            verification_status="DRAFT",
            provisional_score=0.0,
        )
        db.session.add(hw_sub)
        db.session.flush()

    return submission, hw_sub


def save_hardware_draft(
    session_id: int,
    team_id: int,
    data: dict[str, Any],
    screenshot_file: FileStorage | None = None,
) -> tuple[bool, str]:
    """
    Menyimpan draft pengerjaan Pos Hardware tanpa mengunci submission.
    """
    submission, hw_sub = get_or_create_hardware_submission(session_id, team_id)

    if submission.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED):
        return False, "Pengerjaan telah dikirim dan dikunci, draft tidak dapat diubah."

    # Update field yang tersedia
    if "buildcores_url" in data and data["buildcores_url"]:
        hw_sub.buildcores_url = str(data["buildcores_url"]).strip()

    if "total_price" in data and data["total_price"] is not None and str(data["total_price"]).strip() != "":
        try:
            hw_sub.total_price = max(0.0, float(data["total_price"]))
        except (ValueError, TypeError):
            pass

    if "cpu_name" in data:
        hw_sub.cpu_name = str(data["cpu_name"]).strip() or None

    if "cpu_score" in data and data["cpu_score"] is not None and str(data["cpu_score"]).strip() != "":
        try:
            hw_sub.cpu_score = max(0.0, float(data["cpu_score"]))
        except (ValueError, TypeError):
            pass

    if "gpu_name" in data:
        hw_sub.gpu_name = str(data["gpu_name"]).strip() or None

    if "gpu_score" in data and data["gpu_score"] is not None and str(data["gpu_score"]).strip() != "":
        try:
            hw_sub.gpu_score = max(0.0, float(data["gpu_score"]))
        except (ValueError, TypeError):
            pass

    if "ram_capacity_gb" in data and data["ram_capacity_gb"] is not None and str(data["ram_capacity_gb"]).strip() != "":
        try:
            hw_sub.ram_capacity_gb = max(0.0, float(data["ram_capacity_gb"]))
        except (ValueError, TypeError):
            pass

    if "storage_capacity_gb" in data and data["storage_capacity_gb"] is not None and str(data["storage_capacity_gb"]).strip() != "":
        try:
            hw_sub.storage_capacity_gb = max(0.0, float(data["storage_capacity_gb"]))
        except (ValueError, TypeError):
            pass

    if "psu_name" in data:
        hw_sub.psu_name = str(data["psu_name"]).strip() or None

    if "components_summary" in data:
        hw_sub.components_summary = str(data["components_summary"]).strip() or None
    elif "component_summary" in data:
        hw_sub.components_summary = str(data["component_summary"]).strip() or None

    if "build_rationale" in data:
        hw_sub.build_rationale = str(data["build_rationale"]).strip() or None
    elif "rationale" in data:
        hw_sub.build_rationale = str(data["rationale"]).strip() or None

    if "confirmation_checked" in data:
        hw_sub.confirmation_checked = bool(data["confirmation_checked"])
    elif "compliance_confirmed" in data:
        hw_sub.confirmation_checked = bool(data["compliance_confirmed"])

    # Upload berkas screenshot jika disertakan pada draft
    if screenshot_file and screenshot_file.filename:
        valid_img, safe_fn, err_img = validate_and_save_screenshot(screenshot_file)
        if valid_img and safe_fn:
            hw_sub.screenshot_path = safe_fn

    db.session.commit()
    return True, "Draft hasil pengerjaan berhasil disimpan."


def submit_hardware_challenge(
    session_id: int,
    team_id: int,
    form_data: dict[str, Any],
    screenshot_file: FileStorage | None = None,
) -> tuple[bool, str]:
    """
    Final submit pengerjaan Pos Hardware oleh peserta.
    - Memvalidasi seluruh field wajib.
    - Menghitung skor provisional di server.
    - Mengunci submission agar tidak dapat diubah lagi oleh peserta.
    """
    submission, hw_sub = get_or_create_hardware_submission(session_id, team_id)

    if submission.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.TIMED_OUT, SubmissionStatus.GRADED):
        return False, "Hasil pengerjaan tim Anda sudah dikirim sebelumnya dan sedang dalam verifikasi panitia."

    session_obj = submission.session
    now = get_server_now()
    remaining = get_remaining_seconds(session_obj, now)

    # Validasi URL BuildCores
    url = str(form_data.get("buildcores_url") or "").strip()
    is_url_valid, url_err = validate_buildcores_url(url)
    if not is_url_valid:
        return False, url_err or "URL BuildCores tidak valid."

    # Validasi angka positif
    try:
        total_price = float(form_data.get("total_price") or 0.0)
        if total_price <= 0:
            return False, "Total harga PC harus bernilai positif."
    except (TypeError, ValueError):
        return False, "Total harga PC harus berupa angka valid."

    cpu_name = str(form_data.get("cpu_name") or "").strip()
    if not cpu_name:
        return False, "Nama CPU wajib diisi."

    try:
        cpu_score = float(form_data.get("cpu_score") or 0.0)
        if cpu_score < 0:
            return False, "CPU Score tidak boleh bernilai negatif."
    except (TypeError, ValueError):
        return False, "CPU Score harus berupa angka valid."

    gpu_name = str(form_data.get("gpu_name") or "").strip()
    if not gpu_name:
        return False, "Nama GPU wajib diisi."

    try:
        gpu_score = float(form_data.get("gpu_score") or 0.0)
        if gpu_score < 0:
            return False, "GPU Score tidak boleh bernilai negatif."
    except (TypeError, ValueError):
        return False, "GPU Score harus berupa angka valid."

    try:
        ram_gb = float(form_data.get("ram_capacity_gb") or 0.0)
        if ram_gb <= 0:
            return False, "Kapasitas RAM harus bernilai positif (GB)."
    except (TypeError, ValueError):
        return False, "Kapasitas RAM harus berupa angka valid."

    try:
        storage_gb = float(form_data.get("storage_capacity_gb") or 0.0)
        if storage_gb <= 0:
            return False, "Kapasitas Storage harus bernilai positif (GB)."
    except (TypeError, ValueError):
        return False, "Kapasitas Storage harus berupa angka valid."

    psu_name = str(form_data.get("psu_name") or "").strip()
    if not psu_name:
        return False, "Nama/tipe PSU wajib diisi."

    components_summary = str(form_data.get("components_summary") or form_data.get("component_summary") or "").strip()
    if not components_summary:
        return False, "Ringkasan komponen wajib diisi."

    build_rationale = str(form_data.get("build_rationale") or form_data.get("rationale") or "").strip()
    if not build_rationale:
        return False, "Penjelasan alasan pemilihan build wajib diisi."

    conf_val = form_data.get("confirmation_checked")
    if conf_val is None:
        conf_val = form_data.get("compliance_confirmed")
    confirmation_checked = bool(conf_val in (True, "y", "Y", "on", "1", 1, "true", "True"))
    if not confirmation_checked:
        return False, "Anda wajib mencentang pernyataan bahwa data yang diinput sesuai dengan hasil di BuildCores."

    # Tangani unggahan screenshot jika ada berkas baru atau gunakan dari draft sebelumnya
    if screenshot_file and screenshot_file.filename:
        valid_img, safe_fn, err_img = validate_and_save_screenshot(screenshot_file)
        if not valid_img:
            return False, err_img or "Gagal memproses screenshot."
        hw_sub.screenshot_path = safe_fn

    if not hw_sub.screenshot_path:
        return False, "Tangkapan layar (screenshot) hasil BuildCores wajib diunggah."

    # Simpan snapshot paket jika belum tersimpan
    package = session_obj.package or get_assigned_package_for_group(
        session_obj.station_id, session_obj.group_id, session_obj.id
    )
    if package and not submission.package_snapshot:
        submission.package_id = package.id
        submission.package_snapshot = make_package_snapshot(package)

    rules_config = (submission.package_snapshot or {}).get("rules_config") if submission.package_snapshot else (package.rules_config if package else {})
    scoring_config = (submission.package_snapshot or {}).get("scoring_config") if submission.package_snapshot else (package.scoring_config if package else {})

    sub_dict = {
        "total_price": total_price,
        "cpu_score": cpu_score,
        "gpu_score": gpu_score,
        "ram_capacity_gb": ram_gb,
        "storage_capacity_gb": storage_gb,
        "psu_name": psu_name,
        "cpu_name": cpu_name,
        "gpu_name": gpu_name,
        "confirmation_checked": confirmation_checked,
    }

    raw_score, time_bonus, provisional_final, breakdown = calculate_hardware_scores(
        submission_data=sub_dict,
        rules_config=rules_config or {},
        scoring_config=scoring_config or {},
        remaining_seconds=max(0, remaining),
        total_duration_seconds=session_obj.duration_seconds,
        is_admin_verified=False,
    )

    # Perbarui data HardwareSubmission
    hw_sub.buildcores_url = url
    hw_sub.total_price = total_price
    hw_sub.cpu_name = cpu_name
    hw_sub.cpu_score = cpu_score
    hw_sub.gpu_name = gpu_name
    hw_sub.gpu_score = gpu_score
    hw_sub.ram_capacity_gb = ram_gb
    hw_sub.storage_capacity_gb = storage_gb
    hw_sub.psu_name = psu_name
    hw_sub.components_summary = components_summary
    hw_sub.build_rationale = build_rationale
    hw_sub.confirmation_checked = confirmation_checked
    hw_sub.verification_status = "SUBMITTED"
    hw_sub.provisional_score = provisional_final
    hw_sub.score_breakdown = breakdown

    # Kunci submission
    submission.status = SubmissionStatus.SUBMITTED
    submission.submitted_at = now

    db.session.commit()
    return True, "Hasil pengerjaan Pos Hardware berhasil dikirim dan menunggu verifikasi panitia."


submit_hardware_build = submit_hardware_challenge


def review_hardware_submission(
    hardware_submission_id: int | None = None,
    admin_id: int | None = None,
    action: str | None = None,
    corrected_data: dict[str, Any] | None = None,
    reason: str | None = None,
    **kwargs: Any,
) -> tuple[bool, str]:
    """
    Alur verifikasi dan koreksi oleh juri/panitia:
    - Status: SUBMITTED, NEEDS_REVIEW, VERIFIED, REJECTED, SCORED
    - Setiap perubahan dicatat ke hardware_submission_audits
    - Ketika VERIFIED atau SCORED: nilai final dimasukkan ke tabel scores agar tampil di leaderboard resmi.
    """
    sub_id = hardware_submission_id or kwargs.get("submission_id")
    adm_id = admin_id or kwargs.get("reviewer_id")
    act = (action or kwargs.get("verification_status") or "VERIFY").strip().upper()
    rson = reason or kwargs.get("audit_reason") or kwargs.get("reason") or "Verifikasi submission"

    corr = dict(corrected_data or {})
    if "compatibility_passed" in kwargs:
        corr["is_compatible"] = bool(kwargs["compatibility_passed"])
    if "manual_score_override" in kwargs:
        corr["manual_score_override"] = kwargs["manual_score_override"]
    if "reviewer_notes" in kwargs:
        corr["reviewer_notes"] = kwargs["reviewer_notes"]

    hw_sub = db.session.get(HardwareSubmission, sub_id)
    if not hw_sub:
        hw_sub = db.session.scalar(
            db.select(HardwareSubmission).where(HardwareSubmission.submission_id == sub_id)
        )
    if not hw_sub:
        return False, "Submission hardware tidak ditemukan."

    admin = db.session.get(Admin, adm_id)
    if not admin:
        return False, "Admin tidak valid."

    action = act
    corrected_data = corr
    reason = rson

    submission = hw_sub.submission
    session_obj = submission.session
    package = submission.package or (session_obj.package if session_obj else None)
    rules_config = (submission.package_snapshot or {}).get("rules_config") or (package.rules_config if package else {})
    scoring_config = (submission.package_snapshot or {}).get("scoring_config") or (package.scoring_config if package else {})

    old_values = {
        "verification_status": hw_sub.verification_status,
        "is_compatible": hw_sub.is_compatible,
        "total_price": hw_sub.total_price,
        "cpu_score": hw_sub.cpu_score,
        "gpu_score": hw_sub.gpu_score,
        "verified_score": hw_sub.verified_score,
        "reviewer_notes": hw_sub.reviewer_notes,
    }

    new_status = hw_sub.verification_status
    now = get_server_now()

    # Perbarui koreksi jika ada
    if "is_compatible" in corrected_data:
        hw_sub.is_compatible = bool(corrected_data["is_compatible"])

    if "total_price" in corrected_data and corrected_data["total_price"] is not None:
        try:
            hw_sub.total_price = float(corrected_data["total_price"])
        except (ValueError, TypeError):
            pass

    if "cpu_score" in corrected_data and corrected_data["cpu_score"] is not None:
        try:
            hw_sub.cpu_score = float(corrected_data["cpu_score"])
        except (ValueError, TypeError):
            pass

    if "gpu_score" in corrected_data and corrected_data["gpu_score"] is not None:
        try:
            hw_sub.gpu_score = float(corrected_data["gpu_score"])
        except (ValueError, TypeError):
            pass

    if "reviewer_notes" in corrected_data:
        hw_sub.reviewer_notes = str(corrected_data["reviewer_notes"]).strip() or None

    # Tentukan status akhir berdasarkan aksi panitia
    if action in ("VERIFY", "VERIFIED"):
        new_status = "VERIFIED"
    elif action in ("REJECT", "REJECTED"):
        new_status = "REJECTED"
    elif action in ("REQUEST_REVIEW", "NEEDS_REVIEW"):
        new_status = "NEEDS_REVIEW"
    elif action in ("SCORE", "SCORED"):
        new_status = "SCORED"

    hw_sub.verification_status = new_status
    hw_sub.verified_by_admin_id = admin.id
    hw_sub.verified_at = now

    # Hitung skor terverifikasi
    sub_dict = {
        "total_price": hw_sub.total_price,
        "cpu_score": hw_sub.cpu_score,
        "gpu_score": hw_sub.gpu_score,
        "ram_capacity_gb": hw_sub.ram_capacity_gb,
        "storage_capacity_gb": hw_sub.storage_capacity_gb,
        "psu_name": hw_sub.psu_name,
        "cpu_name": hw_sub.cpu_name,
        "gpu_name": hw_sub.gpu_name,
        "is_compatible": hw_sub.is_compatible if hw_sub.is_compatible is not None else True,
        "confirmation_checked": hw_sub.confirmation_checked,
    }

    remaining_s = (hw_sub.score_breakdown or {}).get("time_bonus", {}).get("remaining_seconds", 0)
    total_dur = session_obj.duration_seconds if session_obj and session_obj.duration_seconds else 1800

    raw_score, time_bonus, final_verified, breakdown = calculate_hardware_scores(
        submission_data=sub_dict,
        rules_config=rules_config or {},
        scoring_config=scoring_config or {},
        remaining_seconds=remaining_s,
        total_duration_seconds=total_dur,
        is_admin_verified=True,
    )

    if "manual_score_override" in corrected_data and corrected_data["manual_score_override"] is not None:
        try:
            final_verified = float(corrected_data["manual_score_override"])
        except (ValueError, TypeError):
            pass

    hw_sub.verified_score = final_verified
    hw_sub.score_breakdown = breakdown

    new_values = {
        "verification_status": new_status,
        "is_compatible": hw_sub.is_compatible,
        "total_price": hw_sub.total_price,
        "cpu_score": hw_sub.cpu_score,
        "gpu_score": hw_sub.gpu_score,
        "verified_score": final_verified,
        "reviewer_notes": hw_sub.reviewer_notes,
    }

    # Audit log
    audit_entry = HardwareSubmissionAudit(
        hardware_submission_id=hw_sub.id,
        admin_id=admin.id,
        action=action,
        old_values=old_values,
        new_values=new_values,
        reason=reason.strip() if reason else "Verifikasi hasil pengerjaan Pos Hardware",
    )
    db.session.add(audit_entry)

    # Integrasi ke Score / Leaderboard:
    # Hanya masukkan ke tabel Score jika status VERIFIED atau SCORED
    score_obj = db.session.scalar(db.select(Score).where(Score.submission_id == submission.id))

    if new_status in ("VERIFIED", "SCORED"):
        if score_obj:
            score_obj.raw_score = raw_score
            score_obj.time_bonus = time_bonus
            score_obj.final_score = final_verified
            score_obj.submitted_at = submission.submitted_at or now
        else:
            score_obj = Score(
                submission_id=submission.id,
                raw_score=raw_score,
                time_bonus=time_bonus,
                final_score=final_verified,
                submitted_at=submission.submitted_at or now,
            )
            db.session.add(score_obj)
        submission.status = SubmissionStatus.GRADED
    elif new_status == "REJECTED":
        # Jika ditolak, skor 0 atau hapus dari skor leaderboard
        if score_obj:
            score_obj.raw_score = 0.0
            score_obj.time_bonus = 0.0
            score_obj.final_score = 0.0
        submission.status = SubmissionStatus.SUBMITTED

    db.session.commit()
    return True, f"Submission berhasil diproses dengan status {new_status}."
