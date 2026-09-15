import csv
import io
import os
import time
import uuid
from pathlib import Path
from flask import current_app
from models import Group, Team, db


def get_temp_upload_dir() -> Path:
    """Mendapatkan direktori penyimpanan file sementara di instance/uploads/tmp/."""
    base_instance = Path(current_app.instance_path) if current_app else Path("instance")
    tmp_dir = base_instance / "uploads" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def cleanup_old_temp_files(max_age_seconds: int = 86400):
    """Membersihkan file CSV sementara yang berumur lebih dari max_age_seconds (default 24 jam)."""
    try:
        tmp_dir = get_temp_upload_dir()
        now = time.time()
        for f in tmp_dir.glob("*.csv"):
            if f.is_file() and (now - f.stat().st_mtime > max_age_seconds):
                f.unlink(missing_ok=True)
    except Exception:
        pass


def save_temp_csv(file_storage) -> tuple[str, Path]:
    """Menyimpan file upload sementara dengan nama UUID acak dan mengembalikan token serta path-nya."""
    cleanup_old_temp_files()
    tmp_dir = get_temp_upload_dir()
    file_token = uuid.uuid4().hex
    temp_path = tmp_dir / f"{file_token}.csv"
    file_storage.save(temp_path)
    return file_token, temp_path


def get_temp_file_path(file_token: str) -> Path | None:
    """Mendapatkan path file sementara berdasarkan token yang valid."""
    # Pastikan file_token hanya alfanumerik hex untuk mencegah directory traversal
    if not file_token or not file_token.isalnum():
        return None
    tmp_dir = get_temp_upload_dir()
    temp_path = tmp_dir / f"{file_token}.csv"
    if temp_path.is_file():
        return temp_path
    return None


def cleanup_temp_file(file_token: str):
    """Menghapus file sementara setelah proses selesai atau dibatalkan."""
    path = get_temp_file_path(file_token)
    if path and path.is_file():
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def parse_and_validate_team_csv(file_path: Path) -> dict:
    """
    Membaca dan memvalidasi file CSV tim.
    Mendukung UTF-8 dan UTF-8-BOM (Excel).
    
    Mengembalikan dict dengan format:
    {
        "success": bool,
        "is_valid": bool,
        "header_error": str | None,
        "total_rows": int,
        "valid_rows_count": int,
        "error_rows_count": int,
        "rows": list[dict],
        "summary_errors": list[str]
    }
    """
    if not file_path.is_file():
        return {
            "success": False,
            "is_valid": False,
            "header_error": "File CSV sementara tidak ditemukan di server.",
            "total_rows": 0,
            "valid_rows_count": 0,
            "error_rows_count": 0,
            "rows": [],
            "summary_errors": ["File sementara tidak ditemukan."],
        }

    # Cek ukuran file (maksimal 2MB)
    if file_path.stat().st_size > 2 * 1024 * 1024:
        return {
            "success": False,
            "is_valid": False,
            "header_error": "Ukuran file melebihi batas maksimum 2 MB.",
            "total_rows": 0,
            "valid_rows_count": 0,
            "error_rows_count": 0,
            "rows": [],
            "summary_errors": ["Ukuran file melebihi 2 MB."],
        }

    # Buka dengan utf-8-sig untuk otomatis menangani UTF-8 biasa maupun BOM dari Microsoft Excel
    try:
        with open(file_path, mode="r", encoding="utf-8-sig", newline="") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, mode="r", encoding="latin-1", newline="") as f:
                content = f.read()
        except Exception:
            return {
                "success": False,
                "is_valid": False,
                "header_error": "File tidak dapat dibaca. Pastikan format file adalah CSV ber-encoding UTF-8.",
                "total_rows": 0,
                "valid_rows_count": 0,
                "error_rows_count": 0,
                "rows": [],
                "summary_errors": ["Encoding file tidak didukung."],
            }

    if not content.strip():
        return {
            "success": False,
            "is_valid": False,
            "header_error": "File CSV kosong atau tidak memiliki data.",
            "total_rows": 0,
            "valid_rows_count": 0,
            "error_rows_count": 0,
            "rows": [],
            "summary_errors": ["File kosong."],
        }

    reader = csv.reader(io.StringIO(content))
    try:
        raw_headers = next(reader, None)
    except Exception as e:
        return {
            "success": False,
            "is_valid": False,
            "header_error": f"Gagal membaca header CSV: {str(e)}",
            "total_rows": 0,
            "valid_rows_count": 0,
            "error_rows_count": 0,
            "rows": [],
            "summary_errors": ["Header CSV tidak valid."],
        }

    if not raw_headers:
        return {
            "success": False,
            "is_valid": False,
            "header_error": "Baris header tidak ditemukan pada file CSV.",
            "total_rows": 0,
            "valid_rows_count": 0,
            "error_rows_count": 0,
            "rows": [],
            "summary_errors": ["Header kosong."],
        }

    # Normalisasi header: strip dan lowercase
    normalized_headers = [h.strip().lower() for h in raw_headers]
    required_cols = {"team_code", "team_name", "school", "group"}
    missing_cols = required_cols - set(normalized_headers)

    if missing_cols:
        missing_str = ", ".join(sorted(missing_cols))
        return {
            "success": False,
            "is_valid": False,
            "header_error": f"Kolom wajib tidak ditemukan: {missing_str}",
            "total_rows": 0,
            "valid_rows_count": 0,
            "error_rows_count": 0,
            "rows": [],
            "summary_errors": [f"Header tidak lengkap. Kolom wajib yang hilang: {missing_str}."],
        }

    # Peta indeks kolom
    col_idx = {h: i for i, h in enumerate(normalized_headers)}

    # Ambil data Group dari database untuk validasi
    db_groups = {g.code.upper(): g.id for g in db.session.scalars(db.select(Group)).all()}
    
    # Ambil seluruh team_code yang sudah ada di database untuk validasi duplicate
    existing_teams = db.session.scalars(db.select(Team.team_code)).all()
    existing_db_codes = {tc.strip().upper() for tc in existing_teams}

    seen_csv_codes: dict[str, int] = {}
    parsed_rows: list[dict] = []
    summary_errors: list[str] = []

    row_number = 1  # Baris 1 adalah header
    for raw_row in reader:
        row_number += 1

        # Abaikan baris yang benar-benar kosong
        if not raw_row or not any(cell.strip() for cell in raw_row):
            continue

        team_code_raw = raw_row[col_idx["team_code"]].strip() if col_idx["team_code"] < len(raw_row) else ""
        team_name_raw = raw_row[col_idx["team_name"]].strip() if col_idx["team_name"] < len(raw_row) else ""
        school_raw = raw_row[col_idx["school"]].strip() if col_idx["school"] < len(raw_row) else ""
        group_raw = raw_row[col_idx["group"]].strip() if col_idx["group"] < len(raw_row) else ""

        # Normalisasi
        team_code = team_code_raw.upper()
        team_name = team_name_raw
        school = school_raw
        group_code = group_raw.upper()

        row_errors: list[str] = []
        status = "VALID"

        # Validasi kolom kosong
        if not team_code:
            row_errors.append("team_code wajib diisi.")
        if not team_name:
            row_errors.append("team_name wajib diisi.")
        if not school:
            row_errors.append("school wajib diisi.")
        if not group_code:
            row_errors.append("group wajib diisi.")
        elif group_code not in db_groups:
            avail_groups = ", ".join(sorted(db_groups.keys()))
            row_errors.append(f'Group "{group_raw}" tidak ditemukan di database. Pilihan valid: {avail_groups}.')

        # Validasi duplicate dalam file CSV
        if team_code:
            if team_code in seen_csv_codes:
                prev_line = seen_csv_codes[team_code]
                row_errors.append(f'Kode tim "{team_code}" duplikat dengan baris {prev_line} dalam file CSV.')
                status = "DUPLICATE"
            else:
                seen_csv_codes[team_code] = row_number

            # Validasi duplicate dengan data di database
            if team_code in existing_db_codes:
                row_errors.append(f'Kode tim "{team_code}" sudah terdaftar di database.')
                status = "DUPLICATE"

        if row_errors and status != "DUPLICATE":
            status = "ERROR"

        for err in row_errors:
            summary_errors.append(f"Baris {row_number}: {err}")

        parsed_rows.append({
            "line": row_number,
            "team_code": team_code,
            "team_name": team_name,
            "school": school,
            "group": group_code,
            "group_id": db_groups.get(group_code),
            "status": status,
            "errors": row_errors,
        })

    valid_count = sum(1 for r in parsed_rows if r["status"] == "VALID")
    error_count = len(parsed_rows) - valid_count
    is_valid = (len(parsed_rows) > 0 and error_count == 0)

    return {
        "success": True,
        "is_valid": is_valid,
        "header_error": None,
        "total_rows": len(parsed_rows),
        "valid_rows_count": valid_count,
        "error_rows_count": error_count,
        "rows": parsed_rows,
        "summary_errors": summary_errors,
    }


def execute_team_import(file_token: str) -> tuple[bool, int, str | None]:
    """
    Mengeksekusi import data tim dari file sementara ke database.
    Menerapkan validasi ulang dan transaksi atomik database (All-or-Nothing).
    """
    path = get_temp_file_path(file_token)
    if not path:
        return False, 0, "Sesi file upload sudah kedaluwarsa atau file tidak ditemukan."

    validation = parse_and_validate_team_csv(path)
    if not validation["success"] or not validation["is_valid"]:
        cleanup_temp_file(file_token)
        err_msg = validation.get("header_error") or "Data CSV mengandung kesalahan dan tidak dapat diimport."
        return False, 0, err_msg

    rows = validation["rows"]
    if not rows:
        cleanup_temp_file(file_token)
        return False, 0, "Tidak ada data tim valid yang ditemukan untuk diimport."

    try:
        imported_count = 0
        for r in rows:
            team = Team(
                team_code=r["team_code"],
                team_name=r["team_name"],
                school=r["school"],
                group_id=r["group_id"],
                is_active=True,
            )
            db.session.add(team)
            imported_count += 1

        db.session.commit()
        cleanup_temp_file(file_token)
        return True, imported_count, None

    except Exception as e:
        db.session.rollback()
        cleanup_temp_file(file_token)
        return False, 0, f"Terjadi kesalahan basis data saat melakukan commit: {str(e)}"


def generate_csv_template() -> str:
    """Menghasilkan teks isi template resmi file team.csv."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["team_code", "team_name", "school", "group"])
    writer.writerow(["A01", "Team Alpha", "SMAN 1 Madiun", "A"])
    writer.writerow(["A02", "Team Beta", "SMKN 1 Madiun", "A"])
    writer.writerow(["B01", "Team Gamma", "SMAN 2 Ngawi", "B"])
    writer.writerow(["C01", "Team Delta", "SMAN 1 Caruban", "C"])
    return output.getvalue()
