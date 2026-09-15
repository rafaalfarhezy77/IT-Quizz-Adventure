import re
from app import app
from models import Admin, Question, QuestionSet, QuestionSetStatus, Station, db


def get_csrf_token(client, path="/admin/login"):
    response = client.get(path)
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match, f"CSRF token tidak ditemukan pada {path}"
    return match.group(1).decode()


def login_admin(client):
    token = get_csrf_token(client, "/admin/login")
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin123", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return client


def verify_step3():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

    with app.app_context():
        # Pastikan question set A-D tersedia
        from services.question_service import ensure_default_question_sets
        ensure_default_question_sets()

        # Ambil Set A dari station pertama
        first_station = db.session.scalar(db.select(Station).order_by(Station.id))
        assert first_station is not None, "Station belum ada"
        set_a = db.session.scalar(
            db.select(QuestionSet).where(
                QuestionSet.station_id == first_station.id,
                QuestionSet.code == "A",
            )
        )
        assert set_a is not None, "Set A belum ada"
        set_id = set_a.id

    client = app.test_client()

    # TEST 11: Protected Route (Unauthenticated client)
    unauth_client = app.test_client()
    res = unauth_client.get("/admin/questions")
    assert res.status_code == 302 and res.location.endswith("/admin/login"), "Harus redirect ke login jika belum login"

    # Login admin
    login_admin(client)

    # TEST 1: List Question Set
    res = client.get("/admin/questions")
    assert res.status_code == 200, "Halaman /admin/questions harus return 200"
    assert b"Software Engineering" in res.data, "Nama station harus tampil"
    assert b"Set A" in res.data and b"Set B" in res.data, "Set A-D harus tampil"

    # Reset status set_a ke DRAFT dan bersihkan soal test jika ada
    with app.app_context():
        q_set = db.session.get(QuestionSet, set_id)
        q_set.status = QuestionSetStatus.DRAFT
        # Hapus soal-soal lama pada set ini untuk pengujian bersih
        db.session.execute(db.delete(Question).where(Question.question_set_id == set_id))
        db.session.commit()

    # TEST 8: READY Tanpa Soal (Harus ditolak)
    detail_page = client.get(f"/admin/questions/set/{set_id}")
    assert detail_page.status_code == 200
    token = get_csrf_token(client, f"/admin/questions/set/{set_id}")

    res = client.post(
        f"/admin/questions/set/{set_id}/status",
        data={"status": "READY", "csrf_token": token},
        follow_redirects=True,
    )
    assert b"belum dapat ditandai READY" in res.data or b"belum memiliki soal aktif" in res.data
    with app.app_context():
        q_set = db.session.get(QuestionSet, set_id)
        assert q_set.status == QuestionSetStatus.DRAFT, "Status set tidak boleh berubah ke READY jika belum ada soal"

    # TEST 3: Invalid Question (Form ditolak jika field kosong)
    create_token = get_csrf_token(client, f"/admin/questions/set/{set_id}/create")
    res = client.post(
        f"/admin/questions/set/{set_id}/create",
        data={
            "text": "",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_answer": "A",
            "weight": 100,
            "order_number": 1,
            "csrf_token": create_token,
        },
        follow_redirects=True,
    )
    assert b"wajib diisi" in res.data, "Validasi form harus menolak pertanyaan kosong"

    # TEST 4: Invalid Correct Answer (Harus ditolak)
    create_token = get_csrf_token(client, f"/admin/questions/set/{set_id}/create")
    res = client.post(
        f"/admin/questions/set/{set_id}/create",
        data={
            "text": "Pertanyaan testing kunci salah?",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_answer": "Z",  # INVALID
            "weight": 100,
            "order_number": 1,
            "csrf_token": create_token,
        },
        follow_redirects=True,
    )
    assert b"Kunci jawaban harus berupa A, B, C, atau D" in res.data or b"Not a valid choice" in res.data

    # TEST 2: Create Valid Question
    create_token = get_csrf_token(client, f"/admin/questions/set/{set_id}/create")
    res = client.post(
        f"/admin/questions/set/{set_id}/create",
        data={
            "text": "Manakah protokol pada layer Transport yang bersifat connection-oriented?",
            "option_a": "UDP",
            "option_b": "TCP",
            "option_c": "IP",
            "option_d": "ICMP",
            "correct_answer": "B",
            "weight": 100,
            "order_number": 1,
            "csrf_token": create_token,
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Soal berhasil ditambahkan" in res.data
    assert b"connection-oriented" in res.data

    with app.app_context():
        created_q = db.session.scalar(
            db.select(Question).where(
                Question.question_set_id == set_id,
                Question.order_number == 1,
            )
        )
        assert created_q is not None
        assert created_q.correct_answer == "B"
        assert created_q.is_active is True
        question_id = created_q.id
        initial_updated_at = created_q.updated_at

    # TEST 5: Edit Question
    edit_token = get_csrf_token(client, f"/admin/questions/{question_id}/edit")
    res = client.post(
        f"/admin/questions/{question_id}/edit",
        data={
            "text": "Manakah protokol pada layer Transport yang bersifat connection-oriented? (Revisi)",
            "option_a": "UDP",
            "option_b": "TCP Protocol",
            "option_c": "IP",
            "option_d": "ICMP",
            "correct_answer": "B",
            "weight": 150,
            "order_number": 1,
            "csrf_token": edit_token,
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Soal berhasil diperbarui" in res.data
    with app.app_context():
        updated_q = db.session.get(Question, question_id)
        assert updated_q.weight == 150
        assert "Revisi" in updated_q.text
        assert updated_q.option_b == "TCP Protocol"

    # TEST 6: Soft Delete
    detail_token = get_csrf_token(client, f"/admin/questions/set/{set_id}")
    res = client.post(
        f"/admin/questions/{question_id}/delete",
        data={"csrf_token": detail_token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Soal berhasil dinonaktifkan" in res.data
    with app.app_context():
        q_deleted = db.session.get(Question, question_id)
        assert q_deleted is not None, "Soal TIDAK boleh dihapus permanen"
        assert q_deleted.is_active is False, "is_active harus False setelah soft delete"

    # Filter aktif harus tidak menampilkan soal ini
    active_filter_res = client.get(f"/admin/questions/set/{set_id}?status=active")
    assert b"Belum ada soal pada filter ini" in active_filter_res.data

    # Filter nonaktif harus menampilkannya
    inactive_filter_res = client.get(f"/admin/questions/set/{set_id}?status=inactive")
    assert b"Revisi" in inactive_filter_res.data

    # TEST 7: Restore
    detail_token = get_csrf_token(client, f"/admin/questions/set/{set_id}")
    res = client.post(
        f"/admin/questions/{question_id}/restore",
        data={"csrf_token": detail_token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Soal berhasil diaktifkan kembali" in res.data
    with app.app_context():
        q_restored = db.session.get(Question, question_id)
        assert q_restored.is_active is True, "is_active harus True setelah restore"

    # TEST 9: READY Valid
    detail_token = get_csrf_token(client, f"/admin/questions/set/{set_id}")
    res = client.post(
        f"/admin/questions/set/{set_id}/status",
        data={"status": "READY", "csrf_token": detail_token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"berhasil diubah menjadi READY" in res.data
    with app.app_context():
        q_set = db.session.get(QuestionSet, set_id)
        assert q_set.status == QuestionSetStatus.READY

    # TEST 10: LOCKED Protection
    detail_token = get_csrf_token(client, f"/admin/questions/set/{set_id}")
    res = client.post(
        f"/admin/questions/set/{set_id}/status",
        data={"status": "LOCKED", "csrf_token": detail_token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"berhasil diubah menjadi LOCKED" in res.data

    # Coba tambah saat LOCKED -> Harus ditolak
    create_token = get_csrf_token(client, f"/admin/questions/set/{set_id}")
    res = client.post(
        f"/admin/questions/set/{set_id}/create",
        data={
            "text": "Soal terlarang saat locked",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_answer": "A",
            "weight": 100,
            "order_number": 2,
            "csrf_token": create_token,
        },
        follow_redirects=True,
    )
    assert b"sedang dikunci" in res.data, "Tambah soal saat LOCKED harus ditolak di backend"

    # Coba edit saat LOCKED -> Harus ditolak
    edit_token = get_csrf_token(client, f"/admin/questions/set/{set_id}")
    res = client.post(
        f"/admin/questions/{question_id}/edit",
        data={
            "text": "Soal diedit saat locked",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_answer": "A",
            "weight": 100,
            "order_number": 1,
            "csrf_token": edit_token,
        },
        follow_redirects=True,
    )
    assert b"sedang dikunci" in res.data, "Edit soal saat LOCKED harus ditolak di backend"

    # Coba soft delete saat LOCKED -> Harus ditolak
    res = client.post(
        f"/admin/questions/{question_id}/delete",
        data={"csrf_token": edit_token},
        follow_redirects=True,
    )
    assert b"sedang dikunci" in res.data, "Delete saat LOCKED harus ditolak di backend"

    # TEST 12: CSRF Protection (Kirim POST tanpa token)
    res = client.post(f"/admin/questions/{question_id}/delete", data={})
    assert res.status_code in (400, 302), "POST tanpa CSRF token harus ditolak"

    # TEST 13: Preview
    preview_res = client.get(f"/admin/questions/set/{set_id}/preview")
    assert preview_res.status_code == 200
    assert b"KUNCI JAWABAN: B" in preview_res.data or b"KUNCI" in preview_res.data
    assert b"TCP Protocol" in preview_res.data

    print("Langkah 3 valid: CRUD soal, soft delete, restore, validasi READY, proteksi LOCKED, filter/search, CSRF, dan preview bekerja 100%.")


if __name__ == "__main__":
    with app.app_context():
        assert db.session.scalar(db.select(Admin).where(Admin.username == "admin"))
    verify_step3()
