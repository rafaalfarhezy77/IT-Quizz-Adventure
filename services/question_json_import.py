import io
import json
import math
import time
import uuid
from pathlib import Path
from flask import current_app
from models import Question, QuestionSet, QuestionSetStatus, Station, db


def get_temp_upload_dir() -> Path:
    """Mendapatkan direktori penyimpanan file sementara di instance/uploads/tmp/."""
    base_instance = Path(current_app.instance_path) if current_app else Path("instance")
    tmp_dir = base_instance / "uploads" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def cleanup_old_temp_files(max_age_seconds: int = 86400):
    """Membersihkan file JSON sementara yang berumur lebih dari max_age_seconds (default 24 jam)."""
    try:
        tmp_dir = get_temp_upload_dir()
        now = time.time()
        for f in tmp_dir.glob("*.json"):
            if f.is_file() and (now - f.stat().st_mtime > max_age_seconds):
                f.unlink(missing_ok=True)
    except Exception:
        pass


def save_temp_json(file_storage) -> tuple[str, Path]:
    """Menyimpan file upload JSON sementara dengan UUID acak."""
    cleanup_old_temp_files()
    tmp_dir = get_temp_upload_dir()
    file_token = uuid.uuid4().hex
    temp_path = tmp_dir / f"{file_token}.json"
    file_storage.save(temp_path)
    return file_token, temp_path


def get_temp_file_path(file_token: str) -> Path | None:
    """Mendapatkan path file sementara berdasarkan token yang valid."""
    if not file_token or not file_token.isalnum():
        return None
    tmp_dir = get_temp_upload_dir()
    temp_path = tmp_dir / f"{file_token}.json"
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


def _extract_val(d: dict, *keys, default=None):
    """Mengambil nilai pertama yang ditemukan dari daftar kemungkinan nama key (case-insensitive)."""
    lower_map = {k.lower().strip(): v for k, v in d.items()}
    for k in keys:
        lk = k.lower().strip()
        if lk in lower_map and lower_map[lk] is not None:
            return lower_map[lk]
    return default


def parse_and_validate_question_json(file_path: Path, station_id: int, mode: str = "ADD") -> dict:
    """
    Membaca dan memvalidasi file JSON Bank Soal.
    
    Aturan Validasi:
    1. Format JSON harus valid dan berupa object dictionary.
    2. Pos/Station target harus valid dan aktif di basis data.
    3. Paket soal yang dimuat (Set A-D) tidak boleh berstatus LOCKED di basis data.
    4. Nomor urut soal dalam satu set tidak boleh duplikat.
    5. Kunci jawaban wajib bernilai 'A', 'B', 'C', atau 'D'.
    6. Seluruh pilihan A, B, C, D wajib terisi (tidak boleh kosong/hilang).
    7. Pembagian anggota:
       - Soal 1–3 wajib Anggota 1
       - Soal 4–6 wajib Anggota 2
       - Soal 7–9 wajib Anggota 3
    8. Pada mode UPDATE: external_id wajib disertakan pada tiap soal.
    9. Pada mode ADD: nomor urut dan external_id tidak boleh berbenturan dengan yang sudah ada di DB.
    """
    result = {
        "success": False,
        "is_valid": False,
        "station": None,
        "mode": mode,
        "global_errors": [],
        "sets_summary": {},
        "questions": [],
        "total_questions": 0,
        "valid_count": 0,
        "error_count": 0,
    }

    if mode not in ("ADD", "UPDATE"):
        result["global_errors"].append("Mode impor harus ADD atau UPDATE.")
        return result

    if not file_path.is_file():
        result["global_errors"].append("File JSON sementara tidak ditemukan di server.")
        return result

    if file_path.stat().st_size > 5 * 1024 * 1024:
        result["global_errors"].append("Ukuran file melebihi batas maksimum 5 MB.")
        return result

    # 1. Parsing JSON
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as jde:
        result["global_errors"].append(f"Format berkas JSON tidak valid: {jde.msg} pada baris {jde.lineno}, kolom {jde.colno}.")
        return result
    except Exception as ex:
        result["global_errors"].append(f"Gagal membaca file JSON: {str(ex)}")
        return result

    if not isinstance(data, dict):
        result["global_errors"].append("Struktur JSON root harus berupa objek dictionary.")
        return result

    # 2. Cek Pos / Station
    station = db.session.get(Station, station_id)
    if station is None or not station.is_active:
        result["global_errors"].append(f"Pos target (ID: {station_id}) tidak ditemukan atau tidak aktif.")
        return result

    result["station"] = {
        "id": station.id,
        "name": station.name,
        "mode": station.mode.value,
    }

    # Normalisasi struktur sets dari JSON
    # Mendukung format: {"sets": {"A": [...], "B": [...]}} atau {"A": [...], "B": [...]} atau {"paket": {...}}
    raw_sets = data.get("sets", data.get("paket"))
    if raw_sets is None:
        # Cek apakah kunci root langsung berupa huruf set: "A", "B", "C", "D"
        detected_sets = {}
        for k, v in data.items():
            k_upper = k.strip().upper()
            if k_upper in ("A", "B", "C", "D"):
                detected_sets[k] = v
        if detected_sets:
            raw_sets = detected_sets
        else:
            result["global_errors"].append("Berkas JSON tidak memuat kunci 'sets' atau daftar paket soal (A, B, C, D).")
            return result

    if not isinstance(raw_sets, dict):
        result["global_errors"].append("Kunci 'sets' dalam JSON harus berupa objek pemetaan Set (contoh: {'A': [...], 'B': [...]}).")
        return result

    # Ambil seluruh QuestionSet untuk station ini di DB
    db_question_sets = {
        qs.code.upper(): qs
        for qs in db.session.scalars(
            db.select(QuestionSet).where(QuestionSet.station_id == station.id)
        ).all()
    }

    parsed_questions = []
    sets_summary = {}
    is_software = station.name.strip().lower() == "software engineering"

    # Iterasi setiap Set yang ada dalam JSON
    for set_code_raw, q_list in raw_sets.items():
        set_code = str(set_code_raw).strip().upper()
        if set_code not in ("A", "B", "C", "D"):
            result["global_errors"].append(f"Kode paket '{set_code}' tidak valid. Hanya Set A, B, C, dan D yang didukung.")
            continue

        if set_code in sets_summary:
            result["global_errors"].append(f"Set {set_code} duplikat setelah normalisasi kode.")
            continue

        db_qs = db_question_sets.get(set_code)
        if db_qs is None:
            result["global_errors"].append(f"Paket soal Set {set_code} untuk Pos {station.name} belum terdaftar di basis data.")
            continue

        # Inisialisasi ringkasan set
        sets_summary[set_code] = {
            "set_id": db_qs.id,
            "set_code": set_code,
            "set_name": db_qs.name,
            "db_status": db_qs.status.value,
            "is_locked": db_qs.status == QuestionSetStatus.LOCKED,
            "total_questions": 0,
            "total_weight": 0.0,
            "member_counts": {1: 0, 2: 0, 3: 0},
            "error_count": 0,
            "case_study": db_qs.case_study,
            "case_study_supplied": False,
        }

        if isinstance(q_list, dict):
            envelope = q_list
            q_list = envelope.get("questions")
            if "case_study" in envelope:
                case = envelope["case_study"]
                sets_summary[set_code]["case_study_supplied"] = True
                if (not isinstance(case, dict)
                        or not isinstance(case.get("title"), str)
                        or not case["title"].strip()
                        or not isinstance(case.get("description"), str)
                        or not case["description"].strip()):
                    result["global_errors"].append(f"[Set {set_code}] case_study wajib berisi title dan description berupa teks yang tidak kosong.")
                    sets_summary[set_code]["case_study"] = None
                else:
                    sets_summary[set_code]["case_study"] = {
                        "title": case["title"].strip(), "description": case["description"].strip()
                    }

        # 3. Proteksi Status LOCKED
        if db_qs.status == QuestionSetStatus.LOCKED:
            result["global_errors"].append(
                f"[Set {set_code}] Paket soal berstatus LOCKED di basis data. Paket yang terkunci tidak boleh diubah melalui import. Ubah status paket ke READY/DRAFT terlebih dahulu."
            )

        if not isinstance(q_list, list):
            result["global_errors"].append(f"[Set {set_code}] Isi paket soal harus berupa daftar array soal.")
            continue

        from services.question_service import is_question_set_editable
        editable, reason = is_question_set_editable(db_qs)
        if station.name.lower() == "networking" and not editable:
            result["global_errors"].append(reason)
        if station.name.lower() == "networking" and len(q_list) != 25:
            result["global_errors"].append("Networking wajib memuat tepat 25 soal per set.")
        if is_software and len(q_list) != 9:
            result["global_errors"].append(f"[Set {set_code}] Software Engineering wajib memuat tepat 9 soal, masing-masing 3 soal per anggota.")

        # Kumpulkan soal yang sudah ada di DB untuk set ini untuk validasi mode ADD / UPDATE
        existing_order_numbers = {q.order_number: q for q in db_qs.questions}
        existing_external_ids = {q.external_id: q for q in db_qs.questions if q.external_id}

        seen_set_order_numbers = set()
        seen_set_external_ids = set()

        for idx, q_raw in enumerate(q_list):
            row_errors = []
            if not isinstance(q_raw, dict):
                row_errors.append("Format butir soal harus berupa objek dictionary.")
                parsed_questions.append({
                    "set_code": set_code,
                    "order_number": idx + 1,
                    "member": None,
                    "category": None,
                    "text": str(q_raw)[:50],
                    "option_a": "",
                    "option_b": "",
                    "option_c": "",
                    "option_d": "",
                    "correct_answer": "",
                    "weight": 0.0,
                    "external_id": None,
                    "status": "ERROR",
                    "errors": row_errors,
                })
                sets_summary[set_code]["error_count"] += 1
                continue

            # Cek apakah pos target adalah Pos Networking
            is_networking = (station.name.lower() == "networking")

            # Ekstrak data soal dengan toleransi alias
            order_num_val = _extract_val(q_raw, "order_number", "nomor", "no", "urutan")
            member_val = _extract_val(q_raw, "member", "member_number", "anggota", "giliran")
            category_val = _extract_val(q_raw, "category", "kategori", "topik", default="")
            text_val = _extract_val(q_raw, "text", "pertanyaan", "soal", "question", default="")
            correct_val = _extract_val(q_raw, "correct_answer", "kunci", "kunci_jawaban", "jawaban", "answer", default="")
            weight_val = _extract_val(q_raw, "weight", "bobot", "nilai", "poin", default=1.0 if is_networking else 10.0)
            ext_id_val = _extract_val(q_raw, "external_id", "id_eksternal", "kode_soal", default=None)

            # Metadata khusus Networking
            stage_val = _extract_val(q_raw, "stage", "tahap")
            case_study_val = _extract_val(q_raw, "case_study", "studi_kasus", "skenario", default=None)
            accepted_answers_val = _extract_val(q_raw, "accepted_answers", "jawaban_diterima", "variasi_jawaban", default=None)
            q_type_val = _extract_val(q_raw, "question_type", "type", "tipe")

            # Ekstrak pilihan A-E (mendukung opsi nested 'options' atau flat 'option_a')
            options_dict = _extract_val(q_raw, "options", "pilihan", "opsi")
            if isinstance(options_dict, dict):
                opt_a = _extract_val(options_dict, "A", "option_a", default="")
                opt_b = _extract_val(options_dict, "B", "option_b", default="")
                opt_c = _extract_val(options_dict, "C", "option_c", default="")
                opt_d = _extract_val(options_dict, "D", "option_d", default="")
                opt_e = _extract_val(options_dict, "E", "option_e", default="")
            else:
                opt_a = _extract_val(q_raw, "option_a", "pilihan_a", "opsi_a", default="")
                opt_b = _extract_val(q_raw, "option_b", "pilihan_b", "opsi_b", default="")
                opt_c = _extract_val(q_raw, "option_c", "pilihan_c", "opsi_c", default="")
                opt_d = _extract_val(q_raw, "option_d", "pilihan_d", "opsi_d", default="")
                opt_e = _extract_val(q_raw, "option_e", "pilihan_e", "opsi_e", default="")

            # Validasi Order Number
            try:
                order_number = int(order_num_val)
                if order_number < 1:
                    row_errors.append(f"Nomor urut soal ({order_number}) harus minimal 1.")
            except (TypeError, ValueError):
                order_number = idx + 1
                row_errors.append(f"Nomor urut soal '{order_num_val}' tidak valid (harus angka bulat).")

            loc_prefix = f"[Set {set_code}][Soal #{order_number}]"
            if ext_id_val:
                loc_prefix += f"[ID: {ext_id_val}]"

            # Validasi duplikasi nomor urut dalam set yang sama di file JSON
            if order_number in seen_set_order_numbers:
                row_errors.append(f"{loc_prefix}: Nomor urut #{order_number} duplikat dalam Set {set_code}.")
            seen_set_order_numbers.add(order_number)

            # Validasi Teks Pertanyaan
            text_str = str(text_val).strip() if text_val is not None else ""
            if not text_str:
                row_errors.append(f"{loc_prefix}: Teks pertanyaan tidak boleh kosong.")

            # Penentuan dan Validasi Khusus Networking vs Legacy Station
            opt_a_str = str(opt_a).strip() if opt_a is not None else ""
            opt_b_str = str(opt_b).strip() if opt_b is not None else ""
            opt_c_str = str(opt_c).strip() if opt_c is not None else ""
            opt_d_str = str(opt_d).strip() if opt_d is not None else ""
            opt_e_str = str(opt_e).strip() if opt_e is not None else ""
            correct_clean = str(correct_val).strip() if correct_val is not None else ""
            accepted_answers_list = None
            stage_num = 1
            question_type = "multiple_choice"
            member_num = None

            if is_networking:
                # Tentukan stage
                if stage_val is not None:
                    try:
                        stage_num = int(stage_val)
                        if stage_num not in (1, 2, 3):
                            row_errors.append(f"{loc_prefix}: Nilai tahap ({stage_num}) harus 1, 2, atau 3.")
                    except (ValueError, TypeError):
                        row_errors.append(f"{loc_prefix}: Nilai tahap '{stage_val}' tidak valid.")
                else:
                    if order_number <= 10:
                        stage_num = 1
                    elif order_number <= 20:
                        stage_num = 2
                    else:
                        stage_num = 3

                # Deteksi question_type
                if q_type_val:
                    question_type = str(q_type_val).strip().lower()
                elif stage_num == 1:
                    question_type = "multiple_choice"
                elif stage_num == 2:
                    question_type = "true_false"
                elif stage_num == 3:
                    question_type = "short_text"

                if question_type not in ("multiple_choice", "true_false", "short_text"):
                    row_errors.append(f"{loc_prefix}: Tipe soal '{question_type}' tidak valid. Harus multiple_choice, true_false, atau short_text.")

                # Validasi per tipe soal di Pos Networking
                if question_type == "multiple_choice":
                    # Mendukung minimal 2 dan maksimal 5 pilihan
                    opts_present = {
                        "A": opt_a_str,
                        "B": opt_b_str,
                        "C": opt_c_str,
                        "D": opt_d_str,
                        "E": opt_e_str,
                    }
                    filled_opts = {k: v for k, v in opts_present.items() if v}
                    if len(filled_opts) < 2:
                        row_errors.append(f"{loc_prefix}: Pilihan ganda harus memiliki minimal 2 opsi (ditemukan {len(filled_opts)}).")
                    corr_upper = correct_clean.upper()
                    if corr_upper not in ("A", "B", "C", "D", "E") or corr_upper not in filled_opts:
                        row_errors.append(f"{loc_prefix}: Kunci jawaban '{correct_clean}' harus salah satu dari pilihan yang tersedia ({', '.join(sorted(filled_opts.keys()))}).")
                    correct_clean = corr_upper

                elif question_type == "true_false":
                    corr_lower = correct_clean.lower()
                    if corr_lower in ("benar", "true", "b", "t"):
                        correct_clean = "Benar"
                    elif corr_lower in ("salah", "false", "s", "f"):
                        correct_clean = "Salah"
                    else:
                        row_errors.append(f"{loc_prefix}: Kunci jawaban benar-salah harus 'Benar' atau 'Salah' (ditemukan '{correct_clean}').")

                elif question_type == "short_text":
                    if accepted_answers_val:
                        if isinstance(accepted_answers_val, list):
                            if any(not isinstance(x, str) or not x.strip() for x in accepted_answers_val):
                                row_errors.append(f"{loc_prefix}: Setiap varian jawaban wajib berupa teks tidak kosong.")
                            accepted_answers_list = [x.strip() for x in accepted_answers_val if isinstance(x, str) and x.strip()]
                        elif isinstance(accepted_answers_val, str):
                            accepted_answers_list = [str(accepted_answers_val).strip()]
                    elif correct_clean:
                        accepted_answers_list = [correct_clean]

                    if not accepted_answers_list:
                        row_errors.append(f"{loc_prefix}: Soal isian singkat wajib menyertakan minimal 1 variasi 'accepted_answers'.")

            else:
                # Validasi Standar untuk Pos Legacy (Software Engineering, Cyber Security, dll)
                try:
                    member_num = int(member_val) if member_val is not None else None
                except (TypeError, ValueError):
                    member_num = None
                    row_errors.append(f"{loc_prefix}: Nilai anggota '{member_val}' tidak valid (harus 1, 2, atau 3).")

                if member_num is not None:
                    if member_num not in (1, 2, 3):
                        row_errors.append(f"{loc_prefix}: Anggota ({member_num}) harus bernilai 1, 2, atau 3.")
                    else:
                        if 1 <= order_number <= 3 and member_num != 1:
                            row_errors.append(f"{loc_prefix}: Pembagian anggota tidak sesuai (nomor 1–3 harus untuk Anggota 1, ditemukan Anggota {member_num}).")
                        elif 4 <= order_number <= 6 and member_num != 2:
                            row_errors.append(f"{loc_prefix}: Pembagian anggota tidak sesuai (nomor 4–6 harus untuk Anggota 2, ditemukan Anggota {member_num}).")
                        elif 7 <= order_number <= 9 and member_num != 3:
                            row_errors.append(f"{loc_prefix}: Pembagian anggota tidak sesuai (nomor 7–9 harus untuk Anggota 3, ditemukan Anggota {member_num}).")
                else:
                    row_errors.append(f"{loc_prefix}: Kolom 'anggota' / 'member' (1–3) wajib diisi.")

                if not opt_a_str:
                    row_errors.append(f"{loc_prefix}: Pilihan A belum diisi atau kosong.")
                if not opt_b_str:
                    row_errors.append(f"{loc_prefix}: Pilihan B belum diisi atau kosong.")
                if not opt_c_str:
                    row_errors.append(f"{loc_prefix}: Pilihan C belum diisi atau kosong.")
                if not opt_d_str:
                    row_errors.append(f"{loc_prefix}: Pilihan D belum diisi atau kosong.")

                correct_clean = correct_clean.upper()
                if correct_clean not in ("A", "B", "C", "D"):
                    row_errors.append(f"{loc_prefix}: Kunci jawaban '{correct_val}' tidak valid (harus A, B, C, atau D).")
                if is_software and opt_e_str:
                    row_errors.append(f"{loc_prefix}: Software Engineering hanya menggunakan opsi A–D.")

            # Validasi Bobot Nilai
            try:
                weight_float = float(weight_val)
                if not math.isfinite(weight_float) or weight_float <= 0:
                    row_errors.append(f"{loc_prefix}: Bobot nilai ({weight_float}) harus lebih besar dari 0.")
            except (TypeError, ValueError):
                weight_float = 1.0 if is_networking else 10.0
                row_errors.append(f"{loc_prefix}: Bobot nilai '{weight_val}' tidak valid (harus angka).")

            # Validasi Mode ADD vs UPDATE & external_id
            ext_id_clean = str(ext_id_val).strip() if ext_id_val is not None else None
            if ext_id_clean:
                if ext_id_clean in seen_set_external_ids:
                    row_errors.append(f"{loc_prefix}: external_id '{ext_id_clean}' duplikat dalam Set {set_code}.")
                seen_set_external_ids.add(ext_id_clean)

            if mode == "UPDATE":
                if not ext_id_clean:
                    row_errors.append(f"{loc_prefix}: external_id wajib diisi untuk mode Perbarui (UPDATE).")
            elif mode == "ADD":
                if order_number in existing_order_numbers:
                    row_errors.append(
                        f"{loc_prefix}: Nomor urut #{order_number} sudah ada di database pada Set {set_code}. Gunakan mode Perbarui (UPDATE) jika ingin memperbarui."
                    )
                if ext_id_clean and ext_id_clean in existing_external_ids:
                    row_errors.append(
                        f"{loc_prefix}: external_id '{ext_id_clean}' sudah terdaftar pada soal lain di Set {set_code}."
                    )

            if is_networking:
                from types import SimpleNamespace
                from services.question_service import validate_networking_question
                row_errors.extend(validate_networking_question(SimpleNamespace(order_number=order_number, stage=stage_num, question_type=question_type, text=text_str, weight=weight_float, option_a=opt_a_str, option_b=opt_b_str, option_c=opt_c_str, option_d=opt_d_str, option_e=opt_e_str, correct_answer=correct_clean, accepted_answers=accepted_answers_list)))
            is_row_valid = (len(row_errors) == 0)
            status_row = "VALID" if is_row_valid else "ERROR"

            if is_row_valid:
                sets_summary[set_code]["total_weight"] += weight_float
                if member_num in (1, 2, 3):
                    sets_summary[set_code]["member_counts"][member_num] += 1
            else:
                sets_summary[set_code]["error_count"] += 1

            sets_summary[set_code]["total_questions"] += 1

            parsed_questions.append({
                "set_code": set_code,
                "set_id": db_qs.id,
                "order_number": order_number,
                "member": member_num,
                "stage": stage_num,
                "question_type": question_type,
                "case_study": str(case_study_val).strip() if case_study_val else None,
                "category": str(category_val).strip() if category_val else "",
                "text": text_str,
                "option_a": opt_a_str or None,
                "option_b": opt_b_str or None,
                "option_c": opt_c_str or None,
                "option_d": opt_d_str or None,
                "option_e": opt_e_str or None,
                "correct_answer": correct_clean,
                "accepted_answers": accepted_answers_list,
                "weight": weight_float,
                "external_id": ext_id_clean,
                "status": status_row,
                "errors": row_errors,
            })

        if is_software and seen_set_order_numbers != set(range(1, 10)):
            result["global_errors"].append(f"[Set {set_code}] Nomor soal wajib lengkap 1–9 tanpa duplikat.")

    # Evaluasi Hasil Akhir
    total_q = len(parsed_questions)
    valid_q = sum(1 for q in parsed_questions if q["status"] == "VALID")
    error_q = total_q - valid_q
    has_global_errors = len(result["global_errors"]) > 0

    result["success"] = True
    result["is_valid"] = (total_q > 0 and error_q == 0 and not has_global_errors)
    result["sets_summary"] = sets_summary
    result["questions"] = parsed_questions
    result["total_questions"] = total_q
    result["valid_count"] = valid_q
    result["error_count"] = error_q

    return result


def execute_question_import(file_token: str, station_id: int, mode: str = "ADD") -> tuple[bool, dict, str | None]:
    """
    Mengeksekusi import bank soal ke database secara atomik (All-or-Nothing).
    Jika terjadi kesalahan apapun, seluruh perubahan di-rollback total.
    """
    file_path = get_temp_file_path(file_token)
    if not file_path:
        return False, {}, "Sesi upload file sudah kedaluwarsa atau file tidak ditemukan."

    validation = parse_and_validate_question_json(file_path, station_id, mode)
    if not validation["success"] or not validation["is_valid"]:
        cleanup_temp_file(file_token)
        err_msg = ""
        if validation["global_errors"]:
            err_msg = " ".join(validation["global_errors"])
        else:
            err_msg = f"Ditemukan {validation['error_count']} kesalahan pada data soal JSON. Import dibatalkan."
        return False, {}, err_msg

    questions = validation["questions"]
    if not questions:
        cleanup_temp_file(file_token)
        return False, {}, "Tidak ada data soal valid yang dapat diimport."

    try:
        inserted_count = 0
        updated_count = 0
        affected_sets = set()

        for summary in validation["sets_summary"].values():
            target_set = db.session.get(QuestionSet, summary["set_id"], populate_existing=True)
            if target_set is None or target_set.status == QuestionSetStatus.LOCKED:
                raise ValueError(f"Set {summary['set_code']} terkunci atau tidak tersedia.")
            if summary["case_study_supplied"]:
                target_set.case_study = summary["case_study"]

        for q_data in questions:
            set_id = q_data["set_id"]
            set_code = q_data["set_code"]
            affected_sets.add(set_code)

            # Cek ulang proteksi status locked
            target_set = db.session.get(QuestionSet, set_id)
            if target_set is None or target_set.status == QuestionSetStatus.LOCKED:
                raise ValueError(f"Paket soal Set {set_code} sedang berstatus LOCKED dan tidak dapat dimodifikasi.")

            if mode == "UPDATE":
                ext_id = q_data["external_id"]
                # Cari soal dengan external_id pada question set ini
                existing_question = db.session.scalar(
                    db.select(Question).where(
                        Question.question_set_id == set_id,
                        Question.external_id == ext_id,
                    )
                )

                if existing_question is None and target_set.station.name.lower() == "networking":
                    # Legacy Networking seeds did not assign external_id. Adopt only an
                    # unassigned row with the same order, under the existing UPDATE preview.
                    existing_question = db.session.scalar(db.select(Question).where(Question.question_set_id == set_id, Question.order_number == q_data["order_number"], Question.external_id.is_(None)))
                if existing_question is not None:
                    existing_question.external_id = ext_id
                    # Perbarui data soal yang sudah ada
                    existing_question.text = q_data["text"]
                    existing_question.case_study = q_data.get("case_study")
                    existing_question.option_a = q_data["option_a"]
                    existing_question.option_b = q_data["option_b"]
                    existing_question.option_c = q_data["option_c"]
                    existing_question.option_d = q_data["option_d"]
                    existing_question.option_e = q_data.get("option_e")
                    existing_question.correct_answer = q_data["correct_answer"]
                    existing_question.accepted_answers = q_data.get("accepted_answers")
                    existing_question.weight = q_data["weight"]
                    existing_question.order_number = q_data["order_number"]
                    existing_question.category = q_data["category"]
                    existing_question.member_number = q_data["member"]
                    existing_question.question_type = q_data.get("question_type", "multiple_choice")
                    existing_question.stage = q_data.get("stage", 1)
                    existing_question.is_active = True
                    updated_count += 1
                else:
                    # Jika belum ada di DB, buat baru dengan external_id tersebut
                    new_q = Question(
                        question_set_id=set_id,
                        text=q_data["text"],
                        case_study=q_data.get("case_study"),
                        option_a=q_data["option_a"],
                        option_b=q_data["option_b"],
                        option_c=q_data["option_c"],
                        option_d=q_data["option_d"],
                        option_e=q_data.get("option_e"),
                        correct_answer=q_data["correct_answer"],
                        accepted_answers=q_data.get("accepted_answers"),
                        weight=q_data["weight"],
                        order_number=q_data["order_number"],
                        external_id=ext_id,
                        category=q_data["category"],
                        member_number=q_data["member"],
                        question_type=q_data.get("question_type", "multiple_choice"),
                        stage=q_data.get("stage", 1),
                        is_active=True,
                    )
                    db.session.add(new_q)
                    inserted_count += 1

            else:  # Mode ADD
                new_q = Question(
                    question_set_id=set_id,
                    text=q_data["text"],
                    case_study=q_data.get("case_study"),
                    option_a=q_data["option_a"],
                    option_b=q_data["option_b"],
                    option_c=q_data["option_c"],
                    option_d=q_data["option_d"],
                    option_e=q_data.get("option_e"),
                    correct_answer=q_data["correct_answer"],
                    accepted_answers=q_data.get("accepted_answers"),
                    weight=q_data["weight"],
                    order_number=q_data["order_number"],
                    external_id=q_data["external_id"],
                    category=q_data["category"],
                    member_number=q_data["member"],
                    question_type=q_data.get("question_type", "multiple_choice"),
                    stage=q_data.get("stage", 1),
                    is_active=True,
                )
                db.session.add(new_q)
                inserted_count += 1

        db.session.commit()
        cleanup_temp_file(file_token)
        return True, {
            "inserted": inserted_count,
            "updated": updated_count,
            "affected_sets": sorted(list(affected_sets)),
        }, None

    except Exception as e:
        db.session.rollback()
        cleanup_temp_file(file_token)
        return False, {}, f"Terjadi kegagalan basis data saat commit import: {str(e)}"
