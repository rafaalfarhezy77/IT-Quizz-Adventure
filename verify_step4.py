import io
import re
from app import app
from models import Admin, Group, Team, db
from services.csv_import import get_temp_file_path, parse_and_validate_team_csv


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


def verify_step4():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

    with app.app_context():
        # Pastikan Group A, B, C, D tersedia
        groups = {g.code: g.id for g in db.session.scalars(db.select(Group)).all()}
        assert set(groups.keys()) >= {"A", "B", "C", "D"}, "Group A-D harus tersedia"
        
        # Bersihkan tabel Team untuk pengujian terisolasi
        db.session.execute(db.delete(Team))
        db.session.commit()

    client = app.test_client()

    # TEST 18: Authentication (Unauthenticated access redirected to login)
    unauth_client = app.test_client()
    res = unauth_client.get("/admin/teams")
    assert res.status_code == 302 and res.location.endswith("/admin/login")
    res_import = unauth_client.get("/admin/teams/import")
    assert res_import.status_code == 302 and res_import.location.endswith("/admin/login")

    # Login admin
    login_admin(client)

    # TEST 1: List Team
    res = client.get("/admin/teams")
    assert res.status_code == 200
    assert b"Manajemen Tim" in res.data
    assert b"TAMBAH TIM" in res.data
    assert b"IMPORT CSV" in res.data

    # TEST 20: Template CSV
    res_tpl = client.get("/admin/teams/template.csv")
    assert res_tpl.status_code == 200
    assert res_tpl.headers["Content-Type"].startswith("text/csv")
    assert b"team_code,team_name,school,group" in res_tpl.data

    # TEST 2: Manual Create (A01, Team Alpha, SMAN 1 Madiun, Group A)
    token = get_csrf_token(client, "/admin/teams/create")
    group_a_id = groups["A"]
    res = client.post(
        "/admin/teams/create",
        data={
            "team_code": "a01",  # Test lowercase input -> harus dinormalisasi jadi A01
            "team_name": "Team Alpha",
            "school": "SMAN 1 Madiun",
            "group_id": group_a_id,
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"berhasil ditambahkan" in res.data

    with app.app_context():
        created_team = db.session.scalar(db.select(Team).where(Team.team_code == "A01"))
        assert created_team is not None, "Tim A01 harus tersimpan sebagai uppercase"
        assert created_team.team_name == "Team Alpha"
        assert created_team.is_active is True
        team_id = created_team.id

    # TEST 3: Duplicate Team Code (A01 lagi -> ditolak)
    token = get_csrf_token(client, "/admin/teams/create")
    res = client.post(
        "/admin/teams/create",
        data={
            "team_code": "A01",
            "team_name": "Team Duplicate",
            "school": "SMAN 2 Madiun",
            "group_id": group_a_id,
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert b"sudah terdaftar" in res.data, "Duplicate A01 harus ditolak"

    # TEST 4: Case Duplicate (a01 -> ditolak karena A01 sudah ada)
    token = get_csrf_token(client, "/admin/teams/create")
    res = client.post(
        "/admin/teams/create",
        data={
            "team_code": "  a01  ",
            "team_name": "Team Lower Case",
            "school": "SMAN 3 Madiun",
            "group_id": group_a_id,
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert b"sudah terdaftar" in res.data, "Case duplicate 'a01' harus ditolak"

    # TEST 5: Edit Team (Update nama & sekolah)
    token = get_csrf_token(client, f"/admin/teams/{team_id}/edit")
    res = client.post(
        f"/admin/teams/{team_id}/edit",
        data={
            "team_code": "A01",
            "team_name": "Team Alpha Reborn",
            "school": "SMAN 1 Madiun Unggulan",
            "group_id": group_a_id,
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"berhasil diperbarui" in res.data
    with app.app_context():
        updated_team = db.session.get(Team, team_id)
        assert updated_team.team_name == "Team Alpha Reborn"
        assert updated_team.school == "SMAN 1 Madiun Unggulan"

    # TEST 6: Deactivate (Soft delete)
    token = get_csrf_token(client, "/admin/teams")
    res = client.post(
        f"/admin/teams/{team_id}/deactivate",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"berhasil dinonaktifkan" in res.data
    with app.app_context():
        t = db.session.get(Team, team_id)
        assert t is not None, "Tim tidak boleh dihapus permanen"
        assert t.is_active is False

    # TEST 7: Restore
    token = get_csrf_token(client, "/admin/teams")
    res = client.post(
        f"/admin/teams/{team_id}/restore",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"berhasil diaktifkan kembali" in res.data
    with app.app_context():
        t = db.session.get(Team, team_id)
        assert t.is_active is True

    # TEST 19: CSRF Protection
    res = client.post(f"/admin/teams/{team_id}/deactivate", data={})
    assert res.status_code in (400, 302), "POST tanpa CSRF harus ditolak"

    # TEST 10: Missing Header in CSV
    token = get_csrf_token(client, "/admin/teams/import")
    bad_csv = b"team_code,team_name,group\nA02,Team Beta,A\n"
    res = client.post(
        "/admin/teams/import",
        data={"file": (io.BytesIO(bad_csv), "bad.csv"), "csrf_token": token},
        follow_redirects=True,
    )
    assert b"Kolom wajib tidak ditemukan" in res.data and b"school" in res.data

    # TEST 11: Invalid Group in CSV
    token = get_csrf_token(client, "/admin/teams/import")
    invalid_grp_csv = b"team_code,team_name,school,group\nZ01,Zeta,SMA Z,Z\n"
    res = client.post(
        "/admin/teams/import",
        data={"file": (io.BytesIO(invalid_grp_csv), "invalid_grp.csv"), "csrf_token": token},
        follow_redirects=True,
    )
    assert b"Group" in res.data and b"tidak ditemukan" in res.data
    assert b"ALL-OR-NOTHING" in res.data

    # TEST 12: Duplicate Dalam CSV
    token = get_csrf_token(client, "/admin/teams/import")
    internal_dup_csv = b"team_code,team_name,school,group\nA04,Alpha,SMA A,A\nA04,Beta,SMA B,A\n"
    res = client.post(
        "/admin/teams/import",
        data={"file": (io.BytesIO(internal_dup_csv), "dup.csv"), "csrf_token": token},
        follow_redirects=True,
    )
    assert b"DUPLICATE" in res.data or b"duplikat" in res.data
    assert b"IMPORT DIBLOKIR" in res.data

    # TEST 13: Duplicate dengan Database (A01 sudah ada di database)
    token = get_csrf_token(client, "/admin/teams/import")
    db_dup_csv = b"team_code,team_name,school,group\nA01,Dupe DB,SMA Dupe,A\n"
    res = client.post(
        "/admin/teams/import",
        data={"file": (io.BytesIO(db_dup_csv), "db_dup.csv"), "csrf_token": token},
        follow_redirects=True,
    )
    assert b"sudah terdaftar di database" in res.data
    assert b"IMPORT DIBLOKIR" in res.data

    # TEST 14: Partial Invalid (All-or-Nothing check)
    token = get_csrf_token(client, "/admin/teams/import")
    partial_csv = (
        b"team_code,team_name,school,group\n"
        b"A02,Beta,SMA B,A\n"
        b"A03,Gamma,SMA C,A\n"
        b"A04,,SMA D,A\n"  # Error: team_name kosong
    )
    res = client.post(
        "/admin/teams/import",
        data={"file": (io.BytesIO(partial_csv), "partial.csv"), "csrf_token": token},
        follow_redirects=True,
    )
    assert b"team_name wajib diisi" in res.data
    assert b"IMPORT DIBLOKIR" in res.data
    with app.app_context():
        # Pastikan A02 dan A03 BELUM tersimpan di DB
        assert db.session.scalar(db.select(Team).where(Team.team_code == "A02")) is None

    # TEST 16 & 17 & 8: Valid CSV dengan UTF-8 BOM & Blank rows
    token = get_csrf_token(client, "/admin/teams/import")
    bom = b"\xef\xbb\xbf"  # UTF-8 BOM
    valid_csv_content = (
        bom +
        b"team_code,team_name,school,group\r\n"
        b"\r\n"  # Blank line (harus diabaikan)
        b"A02,Team Beta,SMKN 1 Madiun,A\r\n"
        b"B01,Team Gamma,SMAN 2 Ngawi,B\r\n"
        b"C01,Team Delta,SMAN 1 Caruban,C\r\n"
        b" \r\n"  # Whitespace blank line
        b"D01,Team Epsilon,SMAN 3 Madiun,D\r\n"
    )
    res = client.post(
        "/admin/teams/import",
        data={"file": (io.BytesIO(valid_csv_content), "teams_bom.csv"), "csrf_token": token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"SEMUA DATA VALID (100%)" in res.data
    assert b"Team Beta" in res.data
    assert b"Team Epsilon" in res.data

    # Ekstrak file_token dan CSRF token dari halaman preview
    token_match = re.search(rb'name="file_token"[^>]*value="([^"]+)"', res.data)
    assert token_match, "file_token harus ada pada halaman preview"
    file_token = token_match.group(1).decode()
    confirm_csrf = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', res.data).group(1).decode()

    # TEST 9: Confirm Import
    res_confirm = client.post(
        "/admin/teams/import/confirm",
        data={"file_token": file_token, "csrf_token": confirm_csrf},
        follow_redirects=True,
    )
    assert res_confirm.status_code == 200
    assert b"Import berhasil. 4 tim berhasil ditambahkan" in res_confirm.data

    with app.app_context():
        # Verifikasi bahwa ke-4 tim masuk ke DB
        assert db.session.scalar(db.select(Team).where(Team.team_code == "A02")) is not None
        assert db.session.scalar(db.select(Team).where(Team.team_code == "B01")) is not None
        assert db.session.scalar(db.select(Team).where(Team.team_code == "C01")) is not None
        assert db.session.scalar(db.select(Team).where(Team.team_code == "D01")) is not None

        # Verifikasi file sementara sudah dihapus
        assert get_temp_file_path(file_token) is None, "Temporary file harus sudah dihapus"

    print("Langkah 4 valid: CRUD tim, case-insensitive, soft delete, restore, import CSV, validasi All-or-Nothing, BOM, template CSV, dan CSRF bekerja 100%.")


if __name__ == "__main__":
    with app.app_context():
        assert db.session.scalar(db.select(Admin).where(Admin.username == "admin"))
    verify_step4()
