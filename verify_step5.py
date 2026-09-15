import re
import unittest
from sqlalchemy.pool import StaticPool
from config import Config
from quiz_app import create_app
from models import db, Admin, Station, Group, Team, StationMode
from werkzeug.security import generate_password_hash


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    PARTICIPANT_ACCESS_CODE = "QUEST2026"
    SECRET_KEY = "test-key-step5"


class Step5ParticipantFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Seed Admin
            admin = Admin(username="root_admin", password_hash=generate_password_hash("AdminSecret123!"), is_active=True)
            db.session.add(admin)

            # Seed Stations
            st1 = Station(name="Software Engineering", mode=StationMode.NORMAL, is_active=True)
            st2 = Station(name="Network Defense", mode=StationMode.MEMBER_ROTATION, is_active=True)
            st_inactive = Station(name="Retired Hardware", mode=StationMode.NORMAL, is_active=False)
            db.session.add_all([st1, st2, st_inactive])
            db.session.flush()

            # Seed Groups
            grp_a = Group(code="A")
            grp_b = Group(code="B")
            grp_c = Group(code="C")
            grp_d = Group(code="D")
            db.session.add_all([grp_a, grp_b, grp_c, grp_d])
            db.session.flush()

            # Seed Teams
            t_a1 = Team(team_code="A-01", team_name="Alpha Tech", school="SMK Negeri 1", group_id=grp_a.id, is_active=True)
            t_a2 = Team(team_code="A-02", team_name="Alpha Dev", school="SMA Mandiri", group_id=grp_a.id, is_active=True)
            t_a_inactive = Team(team_code="A-99", team_name="Alpha Ghost", school="SMA 99", group_id=grp_a.id, is_active=False)

            t_b1 = Team(team_code="B-01", team_name="Beta Sec", school="SMA 2", group_id=grp_b.id, is_active=True)
            db.session.add_all([t_a1, t_a2, t_a_inactive, t_b1])
            db.session.commit()

            self.st1_id = st1.id
            self.st2_id = st2.id
            self.grp_a_id = grp_a.id
            self.grp_b_id = grp_b.id
            self.t_a1_id = t_a1.id
            self.t_a2_id = t_a2.id
            self.t_b1_id = t_b1.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def extract_csrf_token(self, html):
        match = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html)
        if not match:
            match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', html)
        assert match is not None, f"CSRF token not found in HTML (length={len(html)}): {html[:300]}"
        return match.group(1)

    # Test 1 — Landing Page
    def test_01_landing_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("PESERTA LOMBA", html)
        self.assertIn("PANITIA / ADMIN", html)
        self.assertIn("/participant/access", html)
        self.assertIn("/admin/login", html)

    # Test 2 — Participant access without code
    def test_02_participant_access_empty(self):
        page = self.client.get("/participant/access")
        self.assertEqual(page.status_code, 200)
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        resp = self.client.post("/participant/access", data={
            "csrf_token": token,
            "access_code": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Kode akses wajib diisi", resp.data.decode("utf-8"))

    # Test 3 — Incorrect access code
    def test_03_participant_access_incorrect(self):
        page = self.client.get("/participant/access")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        resp = self.client.post("/participant/access", data={
            "csrf_token": token,
            "access_code": "WRONG_CODE_99",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Kode akses tidak valid", resp.data.decode("utf-8"))

    # Test 4 — Correct access code
    def test_04_participant_access_correct(self):
        page = self.client.get("/participant/access")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        resp = self.client.post("/participant/access", data={
            "csrf_token": token,
            "access_code": "quest2026",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/station", resp.headers["Location"])

    # Test 5 — Protected station page without authorization
    def test_05_protected_station_page(self):
        resp = self.client.get("/participant/station", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/access", resp.headers["Location"])

    # Helper: Authorize client
    def _authorize(self, client):
        page = client.get("/participant/access")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        resp = client.post("/participant/access", data={"csrf_token": token, "access_code": "QUEST2026"})
        self.assertEqual(resp.status_code, 302)

    # Test 6 — Select Station
    def test_06_select_station(self):
        self._authorize(self.client)
        page = self.client.get("/participant/station")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertIn("Software Engineering", html)
        self.assertNotIn("Retired Hardware", html)

        token = self.extract_csrf_token(html)
        resp = self.client.post("/participant/station", data={
            "csrf_token": token,
            "item_id": str(self.st1_id),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/group", resp.headers["Location"])

    # Test 7 — Select Group
    def test_07_select_group(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        tok_st = self.extract_csrf_token(p_st.data.decode("utf-8"))
        self.client.post("/participant/station", data={"csrf_token": tok_st, "item_id": str(self.st1_id)})

        page = self.client.get("/participant/group")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertIn("KELOMPOK", html)
        self.assertIn("Software Engineering", html)

        token = self.extract_csrf_token(html)
        resp = self.client.post("/participant/group", data={
            "csrf_token": token,
            "item_id": str(self.grp_a_id),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/team", resp.headers["Location"])

    # Test 8 — Team Filter
    def test_08_team_filter(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})

        page = self.client.get("/participant/team")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertIn("Alpha Tech", html)
        self.assertIn("Alpha Dev", html)
        self.assertNotIn("Alpha Ghost", html)
        self.assertNotIn("Beta Sec", html)

    # Test 9 — Manipulated Team (Group mismatch)
    def test_09_manipulated_team(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})

        p_team = self.client.get("/participant/team")
        token = self.extract_csrf_token(p_team.data.decode("utf-8"))

        resp = self.client.post("/participant/team", data={
            "csrf_token": token,
            "item_id": str(self.t_b1_id),
        }, follow_redirects=True)
        self.assertIn("Pilihan tim tidak valid", resp.data.decode("utf-8"))

    # Test 10 — Select Team
    def test_10_select_team(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})

        p_team = self.client.get("/participant/team")
        token = self.extract_csrf_token(p_team.data.decode("utf-8"))
        resp = self.client.post("/participant/team", data={
            "csrf_token": token,
            "item_id": str(self.t_a1_id),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/confirm", resp.headers["Location"])

    # Test 11 — Confirm Page displays full identity
    def test_11_confirm_page_display(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})
        p_team = self.client.get("/participant/team")
        self.client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p_team.data.decode("utf-8")), "item_id": str(self.t_a1_id)})

        page = self.client.get("/participant/confirm")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertIn("Software Engineering", html)
        self.assertIn("KELOMPOK A", html)
        self.assertIn("A-01", html)
        self.assertIn("Alpha Tech", html)
        self.assertIn("SMK Negeri 1", html)

    # Test 12 — Confirm action
    def test_12_confirm_action(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})
        p_team = self.client.get("/participant/team")
        self.client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p_team.data.decode("utf-8")), "item_id": str(self.t_a1_id)})

        p_conf = self.client.get("/participant/confirm")
        token = self.extract_csrf_token(p_conf.data.decode("utf-8"))
        resp = self.client.post("/participant/confirm", data={"csrf_token": token})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/rules", resp.headers["Location"])

    # Test 13 — Rules Page Display
    def test_13_rules_page(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})
        p_team = self.client.get("/participant/team")
        self.client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p_team.data.decode("utf-8")), "item_id": str(self.t_a1_id)})
        p_conf = self.client.get("/participant/confirm")
        self.client.post("/participant/confirm", data={"csrf_token": self.extract_csrf_token(p_conf.data.decode("utf-8"))})

        page = self.client.get("/participant/rules")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertIn("ATURAN PERLOMBAAN", html)
        self.assertIn("Software Engineering", html)
        self.assertIn("KERJA SAMA TIM", html)

    # Test 14 — Accept Rules
    def test_14_accept_rules(self):
        self._authorize(self.client)
        p_st = self.client.get("/participant/station")
        self.client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = self.client.get("/participant/group")
        self.client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})
        p_team = self.client.get("/participant/team")
        self.client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p_team.data.decode("utf-8")), "item_id": str(self.t_a1_id)})
        p_conf = self.client.get("/participant/confirm")
        self.client.post("/participant/confirm", data={"csrf_token": self.extract_csrf_token(p_conf.data.decode("utf-8"))})

        p_rules = self.client.get("/participant/rules")
        token = self.extract_csrf_token(p_rules.data.decode("utf-8"))
        resp = self.client.post("/participant/rules", data={"csrf_token": token})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/waiting", resp.headers["Location"])

    # Test 15 — Waiting Room displays identity & status WAITING
    def test_15_waiting_room_display(self):
        self._complete_to_waiting(self.client)
        resp = self.client.get("/participant/waiting")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("RUANG TUNGGU SESI", html)
        self.assertIn("STATUS: WAITING", html)
        self.assertIn("Software Engineering", html)
        self.assertIn("KELOMPOK A", html)
        self.assertIn("A-01", html)
        self.assertIn("Alpha Tech", html)
        self.assertIn("SMK Negeri 1", html)

    # Test 16 — Refresh Waiting Room retains state
    def test_16_refresh_waiting_room(self):
        self._complete_to_waiting(self.client)
        resp1 = self.client.get("/participant/waiting")
        self.assertEqual(resp1.status_code, 200)
        resp2 = self.client.get("/participant/waiting")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("A-01", resp2.data.decode("utf-8"))

    # Test 17 — Direct Waiting jump without prior selections
    def test_17_direct_waiting_jump(self):
        fresh_client = self.app.test_client()
        resp = fresh_client.get("/participant/waiting", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/access", resp.headers["Location"])

        self._authorize(fresh_client)
        resp2 = fresh_client.get("/participant/waiting", follow_redirects=False)
        self.assertEqual(resp2.status_code, 302)
        self.assertIn("/participant/station", resp2.headers["Location"])

    # Test 18 — Change Station resets downstream
    def test_18_change_station_resets_downstream(self):
        self._complete_to_waiting(self.client)
        p_st = self.client.get("/participant/station")
        token = self.extract_csrf_token(p_st.data.decode("utf-8"))
        resp = self.client.post("/participant/station", data={"csrf_token": token, "item_id": str(self.st2_id)})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/group", resp.headers["Location"])

        resp_jump = self.client.get("/participant/waiting", follow_redirects=False)
        self.assertEqual(resp_jump.status_code, 302)
        self.assertIn("/participant/group", resp_jump.headers["Location"])

    # Test 19 — Change Group resets downstream
    def test_19_change_group_resets_downstream(self):
        self._complete_to_waiting(self.client)
        p_grp = self.client.get("/participant/group")
        token = self.extract_csrf_token(p_grp.data.decode("utf-8"))
        resp = self.client.post("/participant/group", data={"csrf_token": token, "item_id": str(self.grp_b_id)})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/team", resp.headers["Location"])

        resp_jump = self.client.get("/participant/waiting", follow_redirects=False)
        self.assertEqual(resp_jump.status_code, 302)
        self.assertIn("/participant/team", resp_jump.headers["Location"])

    # Test 20 — Inactive Team while in waiting room
    def test_20_inactive_team_handling(self):
        self._complete_to_waiting(self.client)

        with self.app.app_context():
            team = db.session.get(Team, self.t_a1_id)
            team.is_active = False
            db.session.commit()

        resp = self.client.get("/participant/waiting", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/team", resp.headers["Location"])

    # Test 21 — Participant Reset preserves Admin session
    def test_21_participant_reset_preserves_admin(self):
        login_page = self.client.get("/admin/login")
        adm_token = self.extract_csrf_token(login_page.data.decode("utf-8"))
        self.client.post("/admin/login", data={"csrf_token": adm_token, "username": "root_admin", "password": "AdminSecret123!"})

        self._complete_to_waiting(self.client)

        wait_page = self.client.get("/participant/waiting")
        token = self.extract_csrf_token(wait_page.data.decode("utf-8"))

        reset_resp = self.client.post("/participant/reset", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(reset_resp.status_code, 200)

        prot_resp = self.client.get("/participant/station", follow_redirects=False)
        self.assertEqual(prot_resp.status_code, 302)
        self.assertIn("/participant/access", prot_resp.headers["Location"])

        dash_resp = self.client.get("/admin/dashboard")
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn("root_admin", dash_resp.data.decode("utf-8"))

    # Test 22 — CSRF Protection on all participant POST endpoints
    def test_22_csrf_protection(self):
        r1 = self.client.post("/participant/access", data={"access_code": "QUEST2026"})
        self.assertEqual(r1.status_code, 400)

        self._authorize(self.client)

        r2 = self.client.post("/participant/station", data={"item_id": str(self.st1_id)})
        self.assertEqual(r2.status_code, 400)

        r3 = self.client.post("/participant/reset", data={})
        self.assertEqual(r3.status_code, 400)

    # Helper: Walk entire flow to waiting room
    def _complete_to_waiting(self, client):
        self._authorize(client)
        p_st = client.get("/participant/station")
        client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p_st.data.decode("utf-8")), "item_id": str(self.st1_id)})
        p_grp = client.get("/participant/group")
        client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p_grp.data.decode("utf-8")), "item_id": str(self.grp_a_id)})
        p_team = client.get("/participant/team")
        client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p_team.data.decode("utf-8")), "item_id": str(self.t_a1_id)})
        p_conf = client.get("/participant/confirm")
        client.post("/participant/confirm", data={"csrf_token": self.extract_csrf_token(p_conf.data.decode("utf-8"))})
        p_rules = client.get("/participant/rules")
        client.post("/participant/rules", data={"csrf_token": self.extract_csrf_token(p_rules.data.decode("utf-8"))})


if __name__ == "__main__":
    unittest.main()
