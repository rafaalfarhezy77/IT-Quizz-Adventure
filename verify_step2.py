import re

from app import app
from models import Admin, db


def csrf_token(response):
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match, "CSRF token tidak ditemukan"
    return match.group(1).decode()


def verify():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    wrong_client = app.test_client()
    response = wrong_client.get("/admin/login")
    assert response.status_code == 200 and b"Admin Panel" in response.data
    token = csrf_token(response)

    response = wrong_client.post("/admin/login", data={"username": "admin", "password": "salah", "csrf_token": token}, follow_redirects=True)
    assert b"Username atau password salah." in response.data
    with wrong_client.session_transaction() as current_session:
        assert "admin_id" not in current_session

    client = app.test_client()
    login_page = client.get("/admin/login")
    response = client.post("/admin/login", data={"username": "admin", "password": "admin123", "csrf_token": csrf_token(login_page)})
    assert response.status_code == 302 and response.location.endswith("/admin/dashboard"), (response.status_code, response.location, response.data[:200])
    with client.session_transaction() as current_session:
        assert set(current_session).issubset({"admin_id", "_flashes"})

    dashboard = client.get("/admin/dashboard")
    assert dashboard.status_code == 200 and b"Total Station" in dashboard.data and b">4<" in dashboard.data
    for page in ("questions", "teams", "sessions", "results"):
        response = client.get(f"/admin/{page}")
        assert response.status_code == 200 and b"Fondasi halaman sudah siap" in response.data

    logout_page = client.get("/admin/dashboard")
    logout = client.post("/admin/logout", data={"csrf_token": csrf_token(logout_page)})
    assert logout.status_code == 302 and logout.location.endswith("/admin/login"), (logout.status_code, logout.location, logout.data[:200])
    assert client.get("/admin/dashboard").status_code == 302

    with client.session_transaction() as current_session:
        current_session["admin_id"] = 999999
    response = client.get("/admin/dashboard")
    assert response.status_code == 302 and response.location.endswith("/admin/login")

    response = client.post("/admin/login", data={"username": "admin", "password": "admin123"})
    assert response.status_code == 400
    print("Langkah 2 valid: login, hash, session, proteksi route, placeholder, logout, invalid session, dan CSRF bekerja.")


if __name__ == "__main__":
    with app.app_context():
        assert db.session.scalar(db.select(Admin).where(Admin.username == "admin"))
    verify()
