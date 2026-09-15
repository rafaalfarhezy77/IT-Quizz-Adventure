import re
import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy.pool import StaticPool
from config import Config
from quiz_app import create_app
from models import (
    Admin,
    CompetitionSession,
    Group,
    Question,
    QuestionSet,
    QuestionSetStatus,
    SessionStatus,
    Station,
    StationMode,
    Team,
    db,
)
from services.session_service import get_remaining_seconds, get_server_now
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
    SECRET_KEY = "test-key-step6"


class Step6SessionControlTestCase(unittest.TestCase):
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
            db.session.add_all([st1, st2])
            db.session.flush()

            # Seed Groups
            grp_a = Group(code="A")
            grp_b = Group(code="B")
            db.session.add_all([grp_a, grp_b])
            db.session.flush()

            # Seed Teams
            t_a1 = Team(team_code="A-01", team_name="Alpha Tech", school="SMK Negeri 1", group_id=grp_a.id, is_active=True)
            t_a2 = Team(team_code="A-02", team_name="Alpha Dev", school="SMA Mandiri", group_id=grp_a.id, is_active=True)
            t_b1 = Team(team_code="B-01", team_name="Beta Sec", school="SMA 2", group_id=grp_b.id, is_active=True)
            db.session.add_all([t_a1, t_a2, t_b1])
            db.session.flush()

            # Seed QuestionSets:
            # Set A for Station 1 (READY)
            qs_ready1 = QuestionSet(station_id=st1.id, code="A", name="Set A Ready", status=QuestionSetStatus.READY)
            # Set B for Station 1 (DRAFT)
            qs_draft1 = QuestionSet(station_id=st1.id, code="B", name="Set B Draft", status=QuestionSetStatus.DRAFT)
            # Set A for Station 2 (READY)
            qs_st2_ready = QuestionSet(station_id=st2.id, code="A", name="St2 Set A", status=QuestionSetStatus.READY)
            db.session.add_all([qs_ready1, qs_draft1, qs_st2_ready])
            db.session.flush()

            # Add question to qs_ready1 so it has content
            q1 = Question(
                question_set_id=qs_ready1.id,
                text="Apa kepanjangan dari SQL?",
                option_a="Structured Query Language",
                option_b="Simple Query List",
                option_c="Standard Query Logic",
                option_d="System Question Line",
                correct_answer="A",
                weight=1.0,
                order_number=1,
                is_active=True,
            )
            db.session.add(q1)
            db.session.commit()

            self.st1_id = st1.id
            self.st2_id = st2.id
            self.grp_a_id = grp_a.id
            self.grp_b_id = grp_b.id
            self.t_a1_id = t_a1.id
            self.t_a2_id = t_a2.id
            self.t_b1_id = t_b1.id
            self.qs_ready1_id = qs_ready1.id
            self.qs_draft1_id = qs_draft1.id
            self.qs_st2_ready_id = qs_st2_ready.id

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

    def login_admin(self, client):
        page = client.get("/admin/login")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        resp = client.post("/admin/login", data={
            "csrf_token": token,
            "username": "root_admin",
            "password": "AdminSecret123!",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

    def setup_participant(self, client, station_id=None, group_id=None, team_id=None):
        st_id = station_id or self.st1_id
        g_id = group_id or self.grp_a_id
        t_id = team_id or self.t_a1_id

        # 1. Access
        p1 = client.get("/participant/access")
        client.post("/participant/access", data={"csrf_token": self.extract_csrf_token(p1.data.decode("utf-8")), "access_code": "QUEST2026"})
        # 2. Station
        p2 = client.get("/participant/station")
        client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p2.data.decode("utf-8")), "item_id": str(st_id)})
        # 3. Group
        p3 = client.get("/participant/group")
        client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p3.data.decode("utf-8")), "item_id": str(g_id)})
        # 4. Team
        p4 = client.get("/participant/team")
        client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p4.data.decode("utf-8")), "item_id": str(t_id)})
        # 5. Confirm
        p5 = client.get("/participant/confirm")
        client.post("/participant/confirm", data={"csrf_token": self.extract_csrf_token(p5.data.decode("utf-8"))})
        # 6. Rules
        p6 = client.get("/participant/rules")
        client.post("/participant/rules", data={"csrf_token": self.extract_csrf_token(p6.data.decode("utf-8"))})

    # Test 1 — Create Session
    def test_01_create_session(self):
        self.login_admin(self.client)
        page = self.client.get("/admin/sessions/create")
        self.assertEqual(page.status_code, 200)

        token = self.extract_csrf_token(page.data.decode("utf-8"))
        resp = self.client.post("/admin/sessions/create", data={
            "csrf_token": token,
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("berhasil dibuat", html)
        self.assertIn("WAITING", html)

        with self.app.app_context():
            session_obj = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id))
            self.assertIsNotNone(session_obj)
            self.assertEqual(session_obj.status, SessionStatus.WAITING)
            self.assertEqual(session_obj.duration_seconds, 600)

    # Test 2 — Invalid Question Set belonging to another station
    def test_02_invalid_question_set(self):
        self.login_admin(self.client)
        page = self.client.get("/admin/sessions/create")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Pair station 1 with station 2's question set
        resp = self.client.post("/admin/sessions/create", data={
            "csrf_token": token,
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_st2_ready_id),
            "duration_minutes": 10,
        }, follow_redirects=True)
        self.assertIn("bukan milik pos", resp.data.decode("utf-8"))

    # Test 3 — DRAFT Question Set Rejected
    def test_03_draft_set_rejected(self):
        self.login_admin(self.client)
        page = self.client.get("/admin/sessions/create")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        resp = self.client.post("/admin/sessions/create", data={
            "csrf_token": token,
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_draft1_id),
            "duration_minutes": 10,
        }, follow_redirects=True)
        html = resp.data.decode("utf-8")
        self.assertTrue("harus berstatus READY" in html or "Not a valid choice" in html)

        with self.app.app_context():
            from services.session_service import create_session
            with self.assertRaises(ValueError) as ctx:
                create_session(self.st1_id, self.grp_a_id, self.qs_draft1_id, 10)
            self.assertIn("harus berstatus READY", str(ctx.exception))

    # Test 4 — Duplicate Session Prevention
    def test_04_duplicate_session_prevention(self):
        self.login_admin(self.client)
        # Create first session
        page = self.client.get("/admin/sessions/create")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        self.client.post("/admin/sessions/create", data={
            "csrf_token": token,
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })

        # Try creating duplicate
        page2 = self.client.get("/admin/sessions/create")
        token2 = self.extract_csrf_token(page2.data.decode("utf-8"))
        resp = self.client.post("/admin/sessions/create", data={
            "csrf_token": token2,
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        }, follow_redirects=True)
        self.assertIn("Sudah ada sesi berstatus", resp.data.decode("utf-8"))

    # Test 5 — Waiting Participant State
    def test_05_waiting_participant(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        resp = part_client.get("/participant/waiting")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("STATUS: WAITING", resp.data.decode("utf-8"))

    # Test 6 — Start Session
    def test_06_start_session(self):
        self.login_admin(self.client)
        # Create session
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })

        with self.app.app_context():
            s = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id))
            session_id = s.id

        p_det = self.client.get(f"/admin/sessions/{session_id}")
        token = self.extract_csrf_token(p_det.data.decode("utf-8"))
        resp = self.client.post(f"/admin/sessions/{session_id}/start", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("berhasil dimulai", resp.data.decode("utf-8"))

        with self.app.app_context():
            s = db.session.get(CompetitionSession, session_id)
            self.assertEqual(s.status, SessionStatus.RUNNING)
            self.assertIsNotNone(s.started_at)
            self.assertEqual(s.question_set.status, QuestionSetStatus.LOCKED)

    # Test 7 — Double Start Protection
    def test_07_double_start_protection(self):
        self.login_admin(self.client)
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })

        with self.app.app_context():
            s = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id))
            session_id = s.id

        p_det = self.client.get(f"/admin/sessions/{session_id}")
        self.client.post(f"/admin/sessions/{session_id}/start", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))})

        with self.app.app_context():
            orig_start = db.session.get(CompetitionSession, session_id).started_at

        # Second start call
        p_det2 = self.client.get(f"/admin/sessions/{session_id}")
        resp2 = self.client.post(f"/admin/sessions/{session_id}/start", data={"csrf_token": self.extract_csrf_token(p_det2.data.decode("utf-8"))}, follow_redirects=True)
        self.assertIn("sudah berjalan", resp2.data.decode("utf-8").lower())

        with self.app.app_context():
            new_start = db.session.get(CompetitionSession, session_id).started_at
            self.assertEqual(orig_start, new_start)

    # Test 8 — Participant Polling API
    def test_08_participant_polling_api(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        # Before session is created
        r1 = part_client.get("/api/participant/session-status")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.headers.get("Cache-Control"), "no-store, no-cache, must-revalidate, max-age=0")
        data1 = r1.get_json()
        self.assertEqual(data1["status"], "WAITING")
        self.assertFalse(data1["session_found"])

        # Start session via admin
        self.login_admin(self.client)
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })
        with self.app.app_context():
            s = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id))
            session_id = s.id
        p_det = self.client.get(f"/admin/sessions/{session_id}")
        self.client.post(f"/admin/sessions/{session_id}/start", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))})

        # Participant polls now
        r2 = part_client.get("/api/participant/session-status")
        self.assertEqual(r2.status_code, 200)
        data2 = r2.get_json()
        self.assertEqual(data2["status"], "RUNNING")
        self.assertTrue(data2["session_found"])
        self.assertGreater(data2["remaining_seconds"], 590)

    # Test 9 — Auto Redirect / Access to Quiz
    def test_09_access_to_quiz(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        # Before start: quiz should redirect to waiting
        r_pre = part_client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(r_pre.status_code, 302)
        self.assertIn("/participant/waiting", r_pre.headers["Location"])

        # Start session
        self.login_admin(self.client)
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })
        with self.app.app_context():
            session_id = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id)).id
        p_det = self.client.get(f"/admin/sessions/{session_id}")
        self.client.post(f"/admin/sessions/{session_id}/start", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))})

        # After start: quiz is accessible
        r_post = part_client.get("/participant/quiz")
        self.assertEqual(r_post.status_code, 200)
        html = r_post.data.decode("utf-8")
        self.assertIn("SESI PERLOMBAAN SEDANG BERLANGSUNG", html)
        self.assertIn("session-timer", html)

    # Test 10 — Server-side Countdown Accuracy
    def test_10_timer_countdown(self):
        with self.app.app_context():
            session_obj = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=600,
                status=SessionStatus.RUNNING,
                started_at=get_server_now() - timedelta(seconds=65),
            )
            db.session.add(session_obj)
            db.session.commit()

            rem = get_remaining_seconds(session_obj)
            self.assertIn(rem, (534, 535))

    # Test 11 — Refresh Quiz maintains correct timer
    def test_11_refresh_quiz_maintains_timer(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        with self.app.app_context():
            session_obj = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=600,
                status=SessionStatus.RUNNING,
                started_at=get_server_now() - timedelta(seconds=120),
            )
            db.session.add(session_obj)
            db.session.commit()

        resp1 = part_client.get("/participant/quiz")
        self.assertEqual(resp1.status_code, 200)
        html1 = resp1.data.decode("utf-8")
        self.assertTrue(any(t in html1 for t in ("07:59", "08:00", "08:01")))

        # Refresh
        resp2 = part_client.get("/participant/quiz")
        self.assertEqual(resp2.status_code, 200)
        html2 = resp2.data.decode("utf-8")
        self.assertTrue(any(t in html2 for t in ("07:59", "08:00", "08:01")))

    # Test 12 — Multiple Participants in Same Group
    def test_12_multiple_participants_same_group(self):
        client1 = self.app.test_client()
        self.setup_participant(client1, team_id=self.t_a1_id)

        client2 = self.app.test_client()
        self.setup_participant(client2, team_id=self.t_a2_id)

        # Start session
        self.login_admin(self.client)
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })
        with self.app.app_context():
            s_id = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id)).id
        p_det = self.client.get(f"/admin/sessions/{s_id}")
        self.client.post(f"/admin/sessions/{s_id}/start", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))})

        poll1 = client1.get("/api/participant/session-status").get_json()
        poll2 = client2.get("/api/participant/session-status").get_json()
        self.assertEqual(poll1["started_at"], poll2["started_at"])
        self.assertEqual(poll1["duration_seconds"], poll2["duration_seconds"])

    # Test 13 — Server Autoritative Time (Clock Drift)
    def test_13_server_authoritative_time(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        with self.app.app_context():
            s = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=300,
                status=SessionStatus.RUNNING,
                started_at=get_server_now() - timedelta(seconds=100),
            )
            db.session.add(s)
            db.session.commit()

        res = part_client.get("/api/participant/session-status").get_json()
        self.assertEqual(res["duration_seconds"], 300)
        self.assertIn(res["remaining_seconds"], (199, 200))

    # Test 14 — Manual Finish
    def test_14_manual_finish(self):
        self.login_admin(self.client)
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })
        with self.app.app_context():
            s_id = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id)).id

        p_det = self.client.get(f"/admin/sessions/{s_id}")
        self.client.post(f"/admin/sessions/{s_id}/start", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))})

        # Finish session
        p_det2 = self.client.get(f"/admin/sessions/{s_id}")
        resp = self.client.post(f"/admin/sessions/{s_id}/finish", data={"csrf_token": self.extract_csrf_token(p_det2.data.decode("utf-8"))}, follow_redirects=True)
        self.assertIn("berhasil diakhiri", resp.data.decode("utf-8"))

        with self.app.app_context():
            s = db.session.get(CompetitionSession, s_id)
            self.assertEqual(s.status, SessionStatus.FINISHED)
            self.assertIsNotNone(s.ended_at)

    # Test 15 — Timeout Detection
    def test_15_timeout_detection(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        with self.app.app_context():
            s = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=30,
                status=SessionStatus.RUNNING,
                started_at=get_server_now() - timedelta(seconds=35),  # 35s elapsed > 30s duration
            )
            db.session.add(s)
            db.session.commit()

        poll = part_client.get("/api/participant/session-status").get_json()
        self.assertEqual(poll["status"], "FINISHED")
        self.assertEqual(poll["remaining_seconds"], 0)

        # Visiting quiz should redirect to result or session-ended
        resp = part_client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            "/participant/result" in resp.headers["Location"]
            or "/participant/session-ended" in resp.headers["Location"]
        )

    # Test 16 — Cancel Waiting Session
    def test_16_cancel_waiting_session(self):
        self.login_admin(self.client)
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })
        with self.app.app_context():
            s_id = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id)).id

        p_det = self.client.get(f"/admin/sessions/{s_id}")
        resp = self.client.post(f"/admin/sessions/{s_id}/cancel", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))}, follow_redirects=True)
        self.assertIn("berhasil dibatalkan", resp.data.decode("utf-8"))

        with self.app.app_context():
            s = db.session.get(CompetitionSession, s_id)
            self.assertEqual(s.status, SessionStatus.CANCELLED)

    # Test 17 — Edit Running Session Rejected
    def test_17_edit_running_rejected(self):
        self.login_admin(self.client)
        with self.app.app_context():
            s = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=600,
                status=SessionStatus.RUNNING,
                started_at=get_server_now(),
            )
            db.session.add(s)
            db.session.commit()
            s_id = s.id

        # GET edit page should redirect
        r_get = self.client.get(f"/admin/sessions/{s_id}/edit", follow_redirects=True)
        self.assertIn("Hanya sesi WAITING yang dapat diedit", r_get.data.decode("utf-8"))

        # POST edit should be rejected
        p_det = self.client.get(f"/admin/sessions/{s_id}")
        r_post = self.client.post(f"/admin/sessions/{s_id}/edit", data={
            "csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 15,
        }, follow_redirects=True)
        self.assertIn("Hanya sesi WAITING yang dapat diedit", r_post.data.decode("utf-8"))

    # Test 18 — Server Restart Resilience (DB persistence)
    def test_18_server_restart_resilience(self):
        with self.app.app_context():
            started_time = get_server_now() - timedelta(seconds=90)
            s = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=600,
                status=SessionStatus.RUNNING,
                started_at=started_time,
            )
            db.session.add(s)
            db.session.commit()
            s_id = s.id

        # Simulate fresh app instance connected to same storage
        with self.app.app_context():
            loaded_session = db.session.get(CompetitionSession, s_id)
            rem = get_remaining_seconds(loaded_session)
            self.assertIn(rem, (509, 510))

    # Test 19 — Unauthorized Quiz access redirects to waiting
    def test_19_unauthorized_quiz_access(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        resp = part_client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/waiting", resp.headers["Location"])

    # Test 20 — Participant Group B Isolation
    def test_20_participant_group_isolation(self):
        # Start session for Group A
        with self.app.app_context():
            s = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=600,
                status=SessionStatus.RUNNING,
                started_at=get_server_now(),
            )
            db.session.add(s)
            db.session.commit()

        # Participant in Group B
        part_b = self.app.test_client()
        self.setup_participant(part_b, group_id=self.grp_b_id, team_id=self.t_b1_id)

        poll_b = part_b.get("/api/participant/session-status").get_json()
        self.assertEqual(poll_b["status"], "WAITING")
        self.assertFalse(poll_b["session_found"])

        resp_b = part_b.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp_b.status_code, 302)
        self.assertIn("/participant/waiting", resp_b.headers["Location"])

    # Test 21 — CSRF Enforcement on Admin Actions
    def test_21_csrf_enforcement(self):
        self.login_admin(self.client)
        # Create without CSRF
        r1 = self.client.post("/admin/sessions/create", data={"station_id": 1, "group_id": 1, "question_set_id": 1, "duration_minutes": 10})
        self.assertEqual(r1.status_code, 400)

        # Start without CSRF
        r2 = self.client.post("/admin/sessions/1/start", data={})
        self.assertEqual(r2.status_code, 400)

        # Finish without CSRF
        r3 = self.client.post("/admin/sessions/1/finish", data={})
        self.assertEqual(r3.status_code, 400)

        # Cancel without CSRF
        r4 = self.client.post("/admin/sessions/1/cancel", data={})
        self.assertEqual(r4.status_code, 400)

    # Test 22 — API Cache-Control no-store
    def test_22_api_cache_control(self):
        part_client = self.app.test_client()
        self.setup_participant(part_client)

        resp = part_client.get("/api/participant/session-status")
        self.assertIn("no-store", resp.headers.get("Cache-Control", ""))

    # Test 23 — Admin Refresh shows synced timer
    def test_23_admin_refresh_shows_synced_timer(self):
        self.login_admin(self.client)
        with self.app.app_context():
            s = CompetitionSession(
                station_id=self.st1_id,
                group_id=self.grp_a_id,
                question_set_id=self.qs_ready1_id,
                duration_seconds=600,
                status=SessionStatus.RUNNING,
                started_at=get_server_now() - timedelta(seconds=60),
            )
            db.session.add(s)
            db.session.commit()
            s_id = s.id

        resp = self.client.get(f"/admin/sessions/{s_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertTrue(any(t in html for t in ("08:58", "08:59", "09:00", "09:01")))

    # Test 24 — QuestionSet Locked Protection
    def test_24_question_set_locked_protection(self):
        self.login_admin(self.client)
        # Start session to lock question set
        p_c = self.client.get("/admin/sessions/create")
        self.client.post("/admin/sessions/create", data={
            "csrf_token": self.extract_csrf_token(p_c.data.decode("utf-8")),
            "station_id": str(self.st1_id),
            "group_id": str(self.grp_a_id),
            "question_set_id": str(self.qs_ready1_id),
            "duration_minutes": 10,
        })
        with self.app.app_context():
            s_id = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.st1_id)).id
        p_det = self.client.get(f"/admin/sessions/{s_id}")
        self.client.post(f"/admin/sessions/{s_id}/start", data={"csrf_token": self.extract_csrf_token(p_det.data.decode("utf-8"))})

        # Verify QuestionSet is locked
        with self.app.app_context():
            qs = db.session.get(QuestionSet, self.qs_ready1_id)
            self.assertEqual(qs.status, QuestionSetStatus.LOCKED)

        # Attempting to add a question to locked set must be rejected
        add_page = self.client.get(f"/admin/questions/set/{self.qs_ready1_id}/create", follow_redirects=True)
        self.assertIn("dikunci", add_page.data.decode("utf-8").lower())


if __name__ == "__main__":
    unittest.main()
