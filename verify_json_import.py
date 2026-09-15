import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from app import app
from models import Admin, Question, QuestionSet, QuestionSetStatus, Station, db
from services.question_json_import import (
    execute_question_import,
    parse_and_validate_question_json,
    save_temp_json,
)


class TestQuestionJSONImport(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()

        with self.app.app_context():
            # Pastikan station aktif dan question sets tersedia
            station = db.session.scalar(
                db.select(Station).where(Station.name == "Software Engineering")
            )
            self.assertIsNotNone(station, "Station Software Engineering harus ada.")
            self.station_id = station.id

            admin = db.session.scalar(db.select(Admin).where(Admin.username == "admin"))
            self.assertIsNotNone(admin, "Admin user harus ada.")
            self.admin_id = admin.id

            # Pastikan Set A, B, C, D ada
            for code in ("A", "B", "C", "D"):
                qs = db.session.scalar(
                    db.select(QuestionSet).where(
                        QuestionSet.station_id == self.station_id,
                        QuestionSet.code == code,
                    )
                )
                if not qs:
                    qs = QuestionSet(
                        station_id=self.station_id,
                        code=code,
                        name=f"Set {code}",
                        status=QuestionSetStatus.READY,
                    )
                    db.session.add(qs)
                else:
                    qs.status = QuestionSetStatus.READY
            db.session.commit()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["admin_id"] = self.admin_id

    def _create_temp_json_file(self, content_dict):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(content_dict, f)
        return Path(path)

    # --------------------------------------------------------------------------
    # 1. TEST VALIDASI SINTAKS & STRUKTUR JSON
    # --------------------------------------------------------------------------
    def test_invalid_json_syntax(self):
        """Uji file dengan sintaks JSON rusak harus ditolak."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("{ invalid json structure")
        temp_path = Path(path)

        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["success"])
                self.assertFalse(res["is_valid"])
                self.assertTrue(any("Format berkas JSON tidak valid" in err for err in res["global_errors"]))
        finally:
            temp_path.unlink(missing_ok=True)

    def test_missing_sets_key(self):
        """Uji file tanpa kunci sets/paket harus ditolak."""
        temp_path = self._create_temp_json_file({"station": "Software Engineering", "data": []})
        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["is_valid"])
                self.assertTrue(any("tidak memuat kunci 'sets'" in err for err in res["global_errors"]))
        finally:
            temp_path.unlink(missing_ok=True)

    # --------------------------------------------------------------------------
    # 2. TEST VALIDASI DUPLIKASI NOMOR SOAL
    # --------------------------------------------------------------------------
    def test_duplicate_order_number_within_set(self):
        """Uji nomor soal duplikat dalam satu set harus ditolak dengan lokasi jelas."""
        data = {
            "sets": {
                "A": [
                    {
                        "external_id": "SE-A-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Algorithm",
                        "text": "Soal 1",
                        "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                        "correct_answer": "A",
                        "weight": 10.0,
                    },
                    {
                        "external_id": "SE-A-02",
                        "order_number": 1,  # Duplikat!
                        "member": 1,
                        "category": "Algorithm",
                        "text": "Soal 1 Duplikat",
                        "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                        "correct_answer": "B",
                        "weight": 10.0,
                    },
                ]
            }
        }
        temp_path = self._create_temp_json_file(data)
        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["is_valid"])
                self.assertGreater(res["error_count"], 0)
                errors = res["questions"][1]["errors"]
                self.assertTrue(any("Nomor urut #1 duplikat" in err for err in errors))
        finally:
            temp_path.unlink(missing_ok=True)

    # --------------------------------------------------------------------------
    # 3. TEST VALIDASI KUNCI JAWABAN (A, B, C, D)
    # --------------------------------------------------------------------------
    def test_invalid_correct_answer(self):
        """Uji kunci jawaban selain A, B, C, D harus ditolak."""
        data = {
            "sets": {
                "B": [
                    {
                        "external_id": "SE-B-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Algorithm",
                        "text": "Pertanyaan",
                        "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                        "correct_answer": "E",  # Invalid!
                        "weight": 10.0,
                    }
                ]
            }
        }
        temp_path = self._create_temp_json_file(data)
        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["is_valid"])
                errors = res["questions"][0]["errors"]
                self.assertTrue(any("Kunci jawaban 'E' tidak valid" in err for err in errors))
        finally:
            temp_path.unlink(missing_ok=True)

    # --------------------------------------------------------------------------
    # 4. TEST VALIDASI PILIHAN TIDAK LENGKAP
    # --------------------------------------------------------------------------
    def test_incomplete_options(self):
        """Uji jika salah satu opsi (A, B, C, D) kosong atau hilang."""
        data = {
            "sets": {
                "C": [
                    {
                        "external_id": "SE-C-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Algorithm",
                        "text": "Pertanyaan Opsi Kosong",
                        "options": {"A": "Opsi A", "B": "Opsi B", "C": "", "D": "Opsi D"},  # C kosong
                        "correct_answer": "A",
                        "weight": 10.0,
                    }
                ]
            }
        }
        temp_path = self._create_temp_json_file(data)
        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["is_valid"])
                errors = res["questions"][0]["errors"]
                self.assertTrue(any("Pilihan C belum diisi" in err for err in errors))
        finally:
            temp_path.unlink(missing_ok=True)

    # --------------------------------------------------------------------------
    # 5. TEST VALIDASI PEMBAGIAN ANGGOTA (1-3 -> M1, 4-6 -> M2, 7-9 -> M3)
    # --------------------------------------------------------------------------
    def test_member_rotation_partition_rules(self):
        """Uji aturan ketat pembagian nomor soal ke anggota tim."""
        data = {
            "sets": {
                "D": [
                    # Soal 2 dengan Anggota 2 (Harusnya Anggota 1) -> ERROR
                    {
                        "external_id": "SE-D-02",
                        "order_number": 2,
                        "member": 2,
                        "category": "Algorithm",
                        "text": "Soal 2 salah anggota",
                        "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                        "correct_answer": "A",
                        "weight": 10.0,
                    },
                    # Soal 4 dengan Anggota 1 (Harusnya Anggota 2) -> ERROR
                    {
                        "external_id": "SE-D-04",
                        "order_number": 4,
                        "member": 1,
                        "category": "Algorithm",
                        "text": "Soal 4 salah anggota",
                        "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                        "correct_answer": "B",
                        "weight": 10.0,
                    },
                    # Soal 8 dengan Anggota 2 (Harusnya Anggota 3) -> ERROR
                    {
                        "external_id": "SE-D-08",
                        "order_number": 8,
                        "member": 2,
                        "category": "Algorithm",
                        "text": "Soal 8 salah anggota",
                        "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                        "correct_answer": "C",
                        "weight": 10.0,
                    },
                ]
            }
        }
        temp_path = self._create_temp_json_file(data)
        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["is_valid"])
                q0_errs = res["questions"][0]["errors"]
                q1_errs = res["questions"][1]["errors"]
                q2_errs = res["questions"][2]["errors"]

                self.assertTrue(any("nomor 1–3 harus untuk Anggota 1" in e for e in q0_errs))
                self.assertTrue(any("nomor 4–6 harus untuk Anggota 2" in e for e in q1_errs))
                self.assertTrue(any("nomor 7–9 harus untuk Anggota 3" in e for e in q2_errs))
        finally:
            temp_path.unlink(missing_ok=True)

    # --------------------------------------------------------------------------
    # 6. TEST PROTEKSI STATUS LOCKED
    # --------------------------------------------------------------------------
    def test_locked_question_set_protection(self):
        """Uji paket soal berstatus LOCKED tidak boleh diubah melalui import."""
        with self.app.app_context():
            qs_b = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "B",
                )
            )
            qs_b.status = QuestionSetStatus.LOCKED
            db.session.commit()

        data = {
            "sets": {
                "B": [
                    {
                        "external_id": "SE-B-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Algorithm",
                        "text": "Percobaan import pada set locked",
                        "options": {"A": "A", "B": "B", "C": "C", "D": "D"},
                        "correct_answer": "A",
                        "weight": 10.0,
                    }
                ]
            }
        }
        temp_path = self._create_temp_json_file(data)
        try:
            with self.app.app_context():
                res = parse_and_validate_question_json(temp_path, self.station_id, mode="ADD")
                self.assertFalse(res["is_valid"])
                self.assertTrue(any("berstatus LOCKED" in err for err in res["global_errors"]))
        finally:
            temp_path.unlink(missing_ok=True)
            with self.app.app_context():
                qs_b = db.session.scalar(
                    db.select(QuestionSet).where(
                        QuestionSet.station_id == self.station_id,
                        QuestionSet.code == "B",
                    )
                )
                qs_b.status = QuestionSetStatus.READY
                db.session.commit()

    # --------------------------------------------------------------------------
    # 7. TEST MODE TAMBAH (ADD) & ROLLBACK (ALL-OR-NOTHING)
    # --------------------------------------------------------------------------
    def test_add_mode_and_atomic_rollback(self):
        """Uji eksekusi mode ADD dan rollback transaksi jika ada kesalahan."""
        # Bersihkan soal Set C untuk pengujian
        with self.app.app_context():
            qs_c = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "C",
                )
            )
            db.session.execute(db.delete(Question).where(Question.question_set_id == qs_c.id))
            db.session.commit()

        # Data valid untuk Set C (3 soal)
        data = {
            "sets": {
                "C": [
                    {
                        "external_id": "TEST-C-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Programming",
                        "text": "Soal Baru 1",
                        "options": {"A": "P1", "B": "P2", "C": "P3", "D": "P4"},
                        "correct_answer": "A",
                        "weight": 10.0,
                    },
                    {
                        "external_id": "TEST-C-02",
                        "order_number": 2,
                        "member": 1,
                        "category": "Programming",
                        "text": "Soal Baru 2",
                        "options": {"A": "P1", "B": "P2", "C": "P3", "D": "P4"},
                        "correct_answer": "B",
                        "weight": 10.0,
                    },
                    {
                        "external_id": "TEST-C-03",
                        "order_number": 3,
                        "member": 1,
                        "category": "Programming",
                        "text": "Soal Baru 3",
                        "options": {"A": "P1", "B": "P2", "C": "P3", "D": "P4"},
                        "correct_answer": "C",
                        "weight": 10.0,
                    },
                ]
            }
        }

        # Simpan melalui upload helper
        class DummyFile:
            def __init__(self, content):
                self.content = content
            def save(self, target_path):
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(self.content)

        dummy = DummyFile(json.dumps(data))
        with self.app.app_context():
            token, temp_path = save_temp_json(dummy)
            success, stats, err = execute_question_import(token, self.station_id, mode="ADD")
            self.assertTrue(success, f"Import ADD gagal: {err}")
            self.assertEqual(stats["inserted"], 3)

            # Verifikasi masuk ke DB
            qs_c = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "C",
                )
            )
            q_count = len(qs_c.questions)
            self.assertEqual(q_count, 3)

            # Coba impor lagi dengan mode ADD data yang sama -> Harus ditolak (duplikat)
            token2, temp_path2 = save_temp_json(dummy)
            val2 = parse_and_validate_question_json(temp_path2, self.station_id, mode="ADD")
            self.assertFalse(val2["is_valid"], "Mode ADD harus menolak nomor yang sudah ada di DB")

    # --------------------------------------------------------------------------
    # 8. TEST MODE PERBARUI BERDASARKAN external_id (UPDATE)
    # --------------------------------------------------------------------------
    def test_update_mode_by_external_id(self):
        """Uji mode UPDATE berhasil memperbarui soal berdasarkan external_id."""
        with self.app.app_context():
            qs_c = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "C",
                )
            )
            qs_c_id = qs_c.id
            # Pastikan ada soal TEST-C-01
            q1 = db.session.scalar(
                db.select(Question).where(
                    Question.question_set_id == qs_c_id,
                    Question.external_id == "TEST-C-01",
                )
            )
            if not q1:
                q1 = Question(
                    question_set_id=qs_c_id,
                    order_number=1,
                    external_id="TEST-C-01",
                    text="Teks Lama",
                    option_a="A",
                    option_b="B",
                    option_c="C",
                    option_d="D",
                    correct_answer="A",
                    weight=10.0,
                    category="Lama",
                    member_number=1,
                )
                db.session.add(q1)
                db.session.commit()

        # Data pembaruan untuk TEST-C-01
        update_data = {
            "sets": {
                "C": [
                    {
                        "external_id": "TEST-C-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Kategori Baru Terupdate",
                        "text": "Teks Soal Yang Sudah Diperbarui",
                        "options": {"A": "Opsi Baru A", "B": "Opsi Baru B", "C": "Opsi Baru C", "D": "Opsi Baru D"},
                        "correct_answer": "D",
                        "weight": 25.0,
                    }
                ]
            }
        }

        class DummyFile:
            def __init__(self, content):
                self.content = content
            def save(self, target_path):
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(self.content)

        dummy = DummyFile(json.dumps(update_data))
        with self.app.app_context():
            token, temp_path = save_temp_json(dummy)
            success, stats, err = execute_question_import(token, self.station_id, mode="UPDATE")
            self.assertTrue(success, f"Import UPDATE gagal: {err}")
            self.assertEqual(stats["updated"], 1)

            # Verifikasi perubahan di database
            db.session.expire_all()
            q_updated = db.session.scalar(
                db.select(Question).where(
                    Question.question_set_id == qs_c_id,
                    Question.external_id == "TEST-C-01",
                )
            )
            self.assertEqual(q_updated.text, "Teks Soal Yang Sudah Diperbarui")
            self.assertEqual(q_updated.correct_answer, "D")
            self.assertEqual(q_updated.weight, 25.0)
            self.assertEqual(q_updated.category, "Kategori Baru Terupdate")

    # --------------------------------------------------------------------------
    # 9. TEST ATOMIC ROLLBACK (ALL-OR-NOTHING)
    # --------------------------------------------------------------------------
    def test_atomic_rollback_on_failure(self):
        """Uji transaksi All-or-Nothing: jika satu set gagal, seluruh import di-rollback."""
        with self.app.app_context():
            qs_c = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "C",
                )
            )
            db.session.execute(db.delete(Question).where(Question.question_set_id == qs_c.id))
            db.session.commit()

        data = {
            "sets": {
                "C": [
                    {
                        "external_id": "ROLLBACK-C-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Test",
                        "text": "Soal C1",
                        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                        "correct_answer": "A",
                        "weight": 10.0,
                    }
                ],
                "D": [
                    {
                        "external_id": "ROLLBACK-D-01",
                        "order_number": 1,
                        "member": 1,
                        "category": "Test",
                        "text": "Soal D1",
                        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                        "correct_answer": "A",
                        "weight": 10.0,
                    }
                ]
            }
        }

        class DummyFile:
            def __init__(self, content):
                self.content = content
            def save(self, target_path):
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(self.content)

        dummy = DummyFile(json.dumps(data))
        with self.app.app_context():
            token, temp_path = save_temp_json(dummy)

            # Simulasi Set D terkunci
            qs_d = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "D",
                )
            )
            qs_d.status = QuestionSetStatus.LOCKED
            db.session.commit()

            success, stats, err = execute_question_import(token, self.station_id, mode="ADD")
            self.assertFalse(success, "Import harus gagal karena ada set yang LOCKED")
            self.assertIn("LOCKED", err)

            # Verifikasi Rollback: Soal Set C TIDAK boleh tersimpan!
            db.session.expire_all()
            qs_c_after = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == self.station_id,
                    QuestionSet.code == "C",
                )
            )
            self.assertEqual(len(qs_c_after.questions), 0, "Soal Set C harus di-rollback (0 soal tersimpan)")

            # Kembalikan status Set D
            qs_d.status = QuestionSetStatus.READY
            db.session.commit()

    # --------------------------------------------------------------------------
    # 10. TEST OFFICIAL bank_soal.json FILE & HTTP ENDPOINTS
    # --------------------------------------------------------------------------
    def test_official_bank_soal_json_and_endpoints(self):
        """Uji berkas bank_soal.json dan rute antarmuka admin."""
        self._login()

        # 1. Unduh template bank_soal.json
        res_sample = self.client.get("/admin/questions/sample.json")
        self.assertEqual(res_sample.status_code, 200)
        self.assertIn(b"Software Engineering", res_sample.data)
        self.assertIn(b"SE-A-01", res_sample.data)

        # 2. Halaman upload
        res_get = self.client.get("/admin/questions/import")
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b"Import Bank Soal JSON", res_get.data)
        self.assertIn(b"PILIH BERKAS JSON", res_get.data)

        # 3. Upload file resmi bank_soal.json dalam mode UPDATE
        with open("bank_soal.json", "rb") as f:
            data = {
                "file": (io.BytesIO(f.read()), "bank_soal.json"),
                "station_id": self.station_id,
                "mode": "UPDATE",
            }
            res_upload = self.client.post(
                "/admin/questions/import",
                data=data,
                content_type="multipart/form-data",
            )
            self.assertEqual(res_upload.status_code, 200)
            self.assertIn(b"Preview Import Bank Soal", res_upload.data)
            self.assertIn(b"SELURUH SOAL VALID (100%)", res_upload.data)


if __name__ == "__main__":
    unittest.main()
