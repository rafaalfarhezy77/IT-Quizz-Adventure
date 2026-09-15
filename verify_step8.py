import re
import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy.pool import StaticPool
from config import Config
from quiz_app import create_app
from models import (
    Admin,
    Answer,
    CompetitionSession,
    Group,
    Question,
    QuestionSet,
    QuestionSetStatus,
    Score,
    SessionStatus,
    Station,
    StationMode,
    Submission,
    SubmissionStatus,
    Team,
    db,
)
from services.leaderboard_service import (
    calculate_rankings,
    generate_results_csv,
    get_filtered_results,
    get_session_leaderboard,
    get_session_monitoring_data,
    sanitize_csv_cell,
)
from services.scoring_service import finalize_submission
from services.session_service import get_server_now
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
    SECRET_KEY = "test-key-step8"
    TIME_BONUS_PER_SECOND = 1.0


class Step8LeaderboardAdminExportTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Seed Admin
            admin = Admin(username="root_admin", password_hash=generate_password_hash("AdminSecret123!"), is_active=True)
            db.session.add(admin)

            # Seed Stations
            st1 = Station(name="Network Defense", mode=StationMode.NORMAL, is_active=True)
            st2 = Station(name="Software Engineering", mode=StationMode.MEMBER_ROTATION, is_active=True)
            db.session.add_all([st1, st2])
            db.session.flush()

            # Seed Groups
            grp_a = Group(code="A")
            grp_b = Group(code="B")
            db.session.add_all([grp_a, grp_b])
            db.session.flush()

            # Seed Teams
            t_a1 = Team(team_code="A-01", team_name="Alpha Tech", school="SMK Negeri 1", group_id=grp_a.id, is_active=True)
            t_a2 = Team(team_code="A-02", team_name="Beta Dev", school="SMA Mandiri", group_id=grp_a.id, is_active=True)
            t_a3 = Team(team_code="A-03", team_name="Gamma Cyber", school="SMK 2", group_id=grp_a.id, is_active=True)
            t_b1 = Team(team_code="B-01", team_name="Delta Sec", school="SMA 5", group_id=grp_b.id, is_active=True)
            db.session.add_all([t_a1, t_a2, t_a3, t_b1])
            db.session.flush()

            # Seed QuestionSets
            qs1 = QuestionSet(station_id=st1.id, code="A", name="NetSec Set A", status=QuestionSetStatus.READY)
            qs2 = QuestionSet(station_id=st2.id, code="A", name="SoftEng Set A", status=QuestionSetStatus.READY)
            db.session.add_all([qs1, qs2])
            db.session.flush()

            q1 = Question(
                question_set_id=qs1.id,
                text="Protokol web aman?",
                option_a="HTTP",
                option_b="HTTPS",
                option_c="FTP",
                option_d="SSH",
                correct_answer="B",
                weight=50.0,
                order_number=1,
                is_active=True,
            )
            q2 = Question(
                question_set_id=qs1.id,
                text="Port DNS?",
                option_a="53",
                option_b="80",
                option_c="443",
                option_d="22",
                correct_answer="A",
                weight=50.0,
                order_number=2,
                is_active=True,
            )
            db.session.add_all([q1, q2])
            db.session.commit()

            self.st1_id = st1.id
            self.st2_id = st2.id
            self.grp_a_id = grp_a.id
            self.grp_b_id = grp_b.id
            self.t_a1_id = t_a1.id
            self.t_a2_id = t_a2.id
            self.t_a3_id = t_a3.id
            self.t_b1_id = t_b1.id
            self.qs1_id = qs1.id
            self.qs2_id = qs2.id
            self.q1_id = q1.id
            self.q2_id = q2.id

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

        # Access -> Station -> Group -> Team -> Confirm -> Rules
        p1 = client.get("/participant/access")
        client.post("/participant/access", data={"csrf_token": self.extract_csrf_token(p1.data.decode("utf-8")), "access_code": "QUEST2026"})
        p2 = client.get("/participant/station")
        client.post("/participant/station", data={"csrf_token": self.extract_csrf_token(p2.data.decode("utf-8")), "item_id": str(st_id)})
        p3 = client.get("/participant/group")
        client.post("/participant/group", data={"csrf_token": self.extract_csrf_token(p3.data.decode("utf-8")), "item_id": str(g_id)})
        p4 = client.get("/participant/team")
        client.post("/participant/team", data={"csrf_token": self.extract_csrf_token(p4.data.decode("utf-8")), "item_id": str(t_id)})
        p5 = client.get("/participant/confirm")
        client.post("/participant/confirm", data={"csrf_token": self.extract_csrf_token(p5.data.decode("utf-8"))})
        p6 = client.get("/participant/rules")
        client.post("/participant/rules", data={"csrf_token": self.extract_csrf_token(p6.data.decode("utf-8"))})

    def create_and_start_session(self, station_id=None, group_id=None, question_set_id=None, duration_minutes=10):
        st_id = station_id or self.st1_id
        g_id = group_id or self.grp_a_id
        qs_id = question_set_id or self.qs1_id

        with self.app.app_context():
            from services.session_service import create_session, start_session
            sess = create_session(st_id, g_id, qs_id, duration_minutes)
            start_session(sess)
            return sess.id

    # -------------------------------------------------------------------------
    # Test 1: Participant Leaderboard blocked when still IN_PROGRESS
    # -------------------------------------------------------------------------
    def test_01_participant_leaderboard_in_progress_blocked(self):
        self.create_and_start_session()
        self.setup_participant(self.client)

        # Start quiz (status becomes IN_PROGRESS)
        self.client.get("/participant/quiz")

        # Attempting to open leaderboard while quiz is running should redirect to quiz
        resp = self.client.get("/participant/leaderboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/quiz", resp.headers["Location"])

    # -------------------------------------------------------------------------
    # Test 2: Participant Leaderboard accessible after submission is final
    # -------------------------------------------------------------------------
    def test_02_participant_leaderboard_completed_accessible(self):
        sess_id = self.create_and_start_session()
        self.setup_participant(self.client)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=True)

        resp = self.client.get("/participant/leaderboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("KLASEMEN POS: NETWORK DEFENSE", html)
        self.assertIn("Alpha Tech", html)

    # -------------------------------------------------------------------------
    # Test 3: Participant Leaderboard shows ranked teams correctly
    # -------------------------------------------------------------------------
    def test_03_participant_leaderboard_shows_ranked_teams(self):
        sess_id = self.create_and_start_session()

        # Seed scores for team A-01 (lower) and team A-02 (higher)
        with self.app.app_context():
            sub1 = Submission(session_id=sess_id, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess_id, team_id=self.t_a2_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()

            sc1 = Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now())
            sc2 = Score(submission_id=sub2.id, raw_score=50.0, time_bonus=40.0, final_score=90.0, submitted_at=get_server_now())
            db.session.add_all([sc1, sc2])
            db.session.commit()

        self.setup_participant(self.client, team_id=self.t_a1_id)
        resp = self.client.get("/participant/leaderboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")

        # Beta Dev (90.0) should be #1, Alpha Tech (70.0) should be #2 in the rankings table
        tbody_start = html.find("<tbody")
        self.assertNotEqual(tbody_start, -1)
        idx_beta = html.find("Beta Dev", tbody_start)
        idx_alpha = html.find("Alpha Tech", tbody_start)
        self.assertTrue(idx_beta != -1 and idx_alpha != -1)
        self.assertLess(idx_beta, idx_alpha)

    # -------------------------------------------------------------------------
    # Test 4: Participant Leaderboard highlights own team
    # -------------------------------------------------------------------------
    def test_04_participant_leaderboard_team_highlight(self):
        sess_id = self.create_and_start_session()
        with self.app.app_context():
            sub = Submission(session_id=sess_id, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add(sub)
            db.session.flush()
            sc = Score(submission_id=sub.id, raw_score=50.0, time_bonus=30.0, final_score=80.0, submitted_at=get_server_now())
            db.session.add(sc)
            db.session.commit()

        self.setup_participant(self.client, team_id=self.t_a1_id)
        resp = self.client.get("/participant/leaderboard")
        html = resp.data.decode("utf-8")
        self.assertIn("TIM ANDA", html)
        self.assertIn("row-my-team", html)

    # -------------------------------------------------------------------------
    # Test 5: Participant Leaderboard Zero Leakage
    # -------------------------------------------------------------------------
    def test_05_participant_leaderboard_zero_leakage(self):
        sess_id = self.create_and_start_session()
        with self.app.app_context():
            sub = Submission(session_id=sess_id, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add(sub)
            db.session.flush()
            sc = Score(submission_id=sub.id, raw_score=50.0, time_bonus=30.0, final_score=80.0, submitted_at=get_server_now())
            db.session.add(sc)
            db.session.commit()

        self.setup_participant(self.client, team_id=self.t_a1_id)
        resp = self.client.get("/participant/leaderboard")
        html = resp.data.decode("utf-8")

        self.assertNotIn("correct_answer", html)
        self.assertNotIn("data-correct", html)
        self.assertNotIn("Protokol web aman", html)
        self.assertNotIn("Port DNS", html)

    # -------------------------------------------------------------------------
    # Test 6: Tie-breaker 1: final_score DESC
    # -------------------------------------------------------------------------
    def test_06_ranking_tie_breaker_final_score(self):
        items = [
            {"team_code": "A-01", "final_score": 75.0, "raw_score": 50.0, "time_bonus": 25.0, "submitted_at": datetime(2026, 9, 11, 10, 0, 0)},
            {"team_code": "A-02", "final_score": 90.0, "raw_score": 50.0, "time_bonus": 40.0, "submitted_at": datetime(2026, 9, 11, 10, 5, 0)},
        ]
        ranked = calculate_rankings(items)
        self.assertEqual(ranked[0]["team_code"], "A-02")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["team_code"], "A-01")
        self.assertEqual(ranked[1]["rank"], 2)

    # -------------------------------------------------------------------------
    # Test 7: Tie-breaker 2: raw_score DESC
    # -------------------------------------------------------------------------
    def test_07_ranking_tie_breaker_raw_score(self):
        # Same final score (100.0), but A-01 has higher raw score (80 vs 70)
        items = [
            {"team_code": "A-02", "final_score": 100.0, "raw_score": 70.0, "time_bonus": 30.0, "submitted_at": datetime(2026, 9, 11, 10, 0, 0)},
            {"team_code": "A-01", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 20.0, "submitted_at": datetime(2026, 9, 11, 10, 5, 0)},
        ]
        ranked = calculate_rankings(items)
        self.assertEqual(ranked[0]["team_code"], "A-01")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["team_code"], "A-02")
        self.assertEqual(ranked[1]["rank"], 2)

    # -------------------------------------------------------------------------
    # Test 8: Tie-breaker 3: time_bonus DESC
    # -------------------------------------------------------------------------
    def test_08_ranking_tie_breaker_time_bonus(self):
        # Same final score (100.0) and same raw score (80.0), higher time bonus wins
        items = [
            {"team_code": "A-01", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 20.0, "submitted_at": datetime(2026, 9, 11, 10, 5, 0)},
            {"team_code": "A-02", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 25.0, "submitted_at": datetime(2026, 9, 11, 10, 10, 0)},
        ]
        ranked = calculate_rankings(items)
        self.assertEqual(ranked[0]["team_code"], "A-02")
        self.assertEqual(ranked[0]["rank"], 1)

    # -------------------------------------------------------------------------
    # Test 9: Tie-breaker 4: submitted_at ASC (earlier is better)
    # -------------------------------------------------------------------------
    def test_09_ranking_tie_breaker_submitted_at(self):
        t1 = datetime(2026, 9, 11, 10, 2, 0)
        t2 = datetime(2026, 9, 11, 10, 5, 0)
        items = [
            {"team_code": "A-02", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 20.0, "submitted_at": t2},
            {"team_code": "A-01", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 20.0, "submitted_at": t1},
        ]
        ranked = calculate_rankings(items)
        self.assertEqual(ranked[0]["team_code"], "A-01")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["team_code"], "A-02")
        self.assertEqual(ranked[1]["rank"], 2)

    # -------------------------------------------------------------------------
    # Test 10: Tie-breaker 5: exact tie shares rank and sorts by team_code ASC
    # -------------------------------------------------------------------------
    def test_10_ranking_tie_breaker_exact_tie_fallback(self):
        same_time = datetime(2026, 9, 11, 10, 0, 0)
        items = [
            {"team_code": "A-02", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 20.0, "submitted_at": same_time},
            {"team_code": "A-01", "final_score": 100.0, "raw_score": 80.0, "time_bonus": 20.0, "submitted_at": same_time},
            {"team_code": "A-03", "final_score": 80.0, "raw_score": 60.0, "time_bonus": 20.0, "submitted_at": same_time},
        ]
        ranked = calculate_rankings(items)
        self.assertEqual(ranked[0]["team_code"], "A-01")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["team_code"], "A-02")
        self.assertEqual(ranked[1]["rank"], 1)  # shared competition rank
        self.assertEqual(ranked[2]["team_code"], "A-03")
        self.assertEqual(ranked[2]["rank"], 3)  # next rank is 3

    # -------------------------------------------------------------------------
    # Test 11: Participant Leaderboard JSON API
    # -------------------------------------------------------------------------
    def test_11_api_participant_leaderboard_json(self):
        sess_id = self.create_and_start_session()
        with self.app.app_context():
            sub = Submission(session_id=sess_id, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add(sub)
            db.session.flush()
            sc = Score(submission_id=sub.id, raw_score=50.0, time_bonus=30.0, final_score=80.0, submitted_at=get_server_now())
            db.session.add(sc)
            db.session.commit()

        self.setup_participant(self.client, team_id=self.t_a1_id)
        resp = self.client.get("/api/participant/leaderboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("no-store", resp.headers["Cache-Control"])
        data = resp.get_json()
        self.assertEqual(data["station_name"], "Network Defense")
        self.assertEqual(data["group_code"], "A")
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["rows"][0]["team_code"], "A-01")
        self.assertTrue(data["rows"][0]["is_my_team"])

    # -------------------------------------------------------------------------
    # Test 12: Zero Answer Leakage in Participant Leaderboard API
    # -------------------------------------------------------------------------
    def test_12_api_participant_leaderboard_zero_leakage(self):
        sess_id = self.create_and_start_session()
        self.setup_participant(self.client, team_id=self.t_a1_id)
        resp = self.client.get("/api/participant/leaderboard")
        text = resp.data.decode("utf-8")
        self.assertNotIn("correct_answer", text)
        self.assertNotIn("kunci", text)

    # -------------------------------------------------------------------------
    # Test 13: Admin Results Index & Backward Compatibility
    # -------------------------------------------------------------------------
    def test_13_admin_results_index_access_and_compatibility(self):
        self.login_admin(self.client)
        resp = self.client.get("/admin/results")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("HASIL LOMBA & REKAPITULASI NILAI", html)
        # Required hidden span for verify_step2.py backward compatibility
        self.assertIn("Fondasi halaman sudah siap", html)

    # -------------------------------------------------------------------------
    # Test 14: Admin Results Filter by Station
    # -------------------------------------------------------------------------
    def test_14_admin_results_filter_by_station(self):
        self.login_admin(self.client)
        sess1 = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)
        sess2 = self.create_and_start_session(station_id=self.st2_id, group_id=self.grp_b_id, question_set_id=self.qs2_id)

        with self.app.app_context():
            sub1 = Submission(session_id=sess1, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess2, team_id=self.t_b1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()
            db.session.add_all([
                Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now()),
                Score(submission_id=sub2.id, raw_score=40.0, time_bonus=10.0, final_score=50.0, submitted_at=get_server_now()),
            ])
            db.session.commit()

        # Filter station 1 (Network Defense)
        resp = self.client.get(f"/admin/results?station_id={self.st1_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Alpha Tech", html)
        self.assertNotIn("Delta Sec", html)

    # -------------------------------------------------------------------------
    # Test 15: Admin Results Filter by Group
    # -------------------------------------------------------------------------
    def test_15_admin_results_filter_by_group(self):
        self.login_admin(self.client)
        sess1 = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)
        sess2 = self.create_and_start_session(station_id=self.st2_id, group_id=self.grp_b_id, question_set_id=self.qs2_id)

        with self.app.app_context():
            sub1 = Submission(session_id=sess1, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess2, team_id=self.t_b1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()
            db.session.add_all([
                Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now()),
                Score(submission_id=sub2.id, raw_score=40.0, time_bonus=10.0, final_score=50.0, submitted_at=get_server_now()),
            ])
            db.session.commit()

        # Filter Group B
        resp = self.client.get(f"/admin/results?group_id={self.grp_b_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Delta Sec", html)
        self.assertNotIn("Alpha Tech", html)

    # -------------------------------------------------------------------------
    # Test 16: Admin Results Filter by Status
    # -------------------------------------------------------------------------
    def test_16_admin_results_filter_by_status(self):
        self.login_admin(self.client)
        sess = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)

        with self.app.app_context():
            sub1 = Submission(session_id=sess, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess, team_id=self.t_a2_id, status=SubmissionStatus.TIMED_OUT, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()
            db.session.add_all([
                Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now()),
                Score(submission_id=sub2.id, raw_score=25.0, time_bonus=0.0, final_score=25.0, submitted_at=get_server_now()),
            ])
            db.session.commit()

        # Filter TIMED_OUT only
        resp = self.client.get("/admin/results?status=TIMED_OUT")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Beta Dev", html)
        self.assertNotIn("Alpha Tech", html)

    # -------------------------------------------------------------------------
    # Test 17: Admin Results Search Query
    # -------------------------------------------------------------------------
    def test_17_admin_results_search_query(self):
        self.login_admin(self.client)
        sess = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)

        with self.app.app_context():
            sub1 = Submission(session_id=sess, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess, team_id=self.t_a2_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()
            db.session.add_all([
                Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now()),
                Score(submission_id=sub2.id, raw_score=50.0, time_bonus=10.0, final_score=60.0, submitted_at=get_server_now()),
            ])
            db.session.commit()

        # Search by school "Mandiri"
        resp = self.client.get("/admin/results?q=Mandiri")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Beta Dev", html)
        self.assertNotIn("Alpha Tech", html)

    # -------------------------------------------------------------------------
    # Test 18: Admin Result Detail Audit View
    # -------------------------------------------------------------------------
    def test_18_admin_results_detail_audit(self):
        self.login_admin(self.client)
        sess = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)

        with self.app.app_context():
            sub = Submission(session_id=sess, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add(sub)
            db.session.flush()
            # Answer 1 correct (B), Answer 2 incorrect (C)
            ans1 = Answer(submission_id=sub.id, question_id=self.q1_id, selected_answer="B", is_correct=True, points_awarded=50.0)
            ans2 = Answer(submission_id=sub.id, question_id=self.q2_id, selected_answer="C", is_correct=False, points_awarded=0.0)
            sc = Score(submission_id=sub.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now())
            db.session.add_all([ans1, ans2, sc])
            db.session.commit()
            sub_id = sub.id

        resp = self.client.get(f"/admin/results/{sub_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("RINCIAN PENILAIAN TIM: ALPHA TECH", html)
        self.assertIn("LEMBAR AUDIT JAWABAN PESERTA", html)
        # Should display official correct answers
        self.assertIn("Protokol web aman?", html)
        self.assertIn("BENAR", html)
        self.assertIn("SALAH", html)

    # -------------------------------------------------------------------------
    # Test 19: Admin Result Detail 404 on invalid ID
    # -------------------------------------------------------------------------
    def test_19_admin_results_detail_non_existent_404(self):
        self.login_admin(self.client)
        resp = self.client.get("/admin/results/99999", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/results", resp.headers["Location"])

    # -------------------------------------------------------------------------
    # Test 20: Session Detail Team Monitoring Section
    # -------------------------------------------------------------------------
    def test_20_admin_session_monitoring_data_in_session_detail(self):
        self.login_admin(self.client)
        sess = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)

        # Team A-01 submitted, Team A-02 in progress, Team A-03 not started
        with self.app.app_context():
            sub1 = Submission(session_id=sess, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess, team_id=self.t_a2_id, status=SubmissionStatus.IN_PROGRESS, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()
            sc1 = Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now())
            db.session.add(sc1)
            db.session.commit()

        resp = self.client.get(f"/admin/sessions/{sess}")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("MONITORING STATUS TIM PESERTA", html)
        self.assertIn("Submitted: 1", html)
        self.assertIn("In Progress: 1", html)
        self.assertIn("Belum Mulai: 1", html)

    # -------------------------------------------------------------------------
    # Test 21: Admin Session Monitoring JSON API
    # -------------------------------------------------------------------------
    def test_21_admin_session_monitoring_api(self):
        self.login_admin(self.client)
        sess = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)

        with self.app.app_context():
            sub = Submission(session_id=sess, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add(sub)
            db.session.flush()
            sc = Score(submission_id=sub.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now())
            db.session.add(sc)
            db.session.commit()

        resp = self.client.get(f"/api/admin/sessions/{sess}/monitoring")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["session_id"], sess)
        self.assertEqual(data["summary"]["submitted"], 1)
        self.assertEqual(data["summary"]["total_teams"], 3)

    # -------------------------------------------------------------------------
    # Test 22: CSV Export Headers and Content
    # -------------------------------------------------------------------------
    def test_22_csv_export_headers_and_content(self):
        self.login_admin(self.client)
        sess = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)

        with self.app.app_context():
            sub = Submission(session_id=sess, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add(sub)
            db.session.flush()
            sc = Score(submission_id=sub.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now())
            db.session.add(sc)
            db.session.commit()

        resp = self.client.get("/admin/results/export.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers["Content-Type"])
        self.assertIn("attachment; filename=", resp.headers["Content-Disposition"])
        content = resp.data.decode("utf-8")
        self.assertIn("rank,team_code,team_name,school,station,group,raw_score,time_bonus,final_score,status,submitted_at", content)
        self.assertIn("A-01,Alpha Tech,SMK Negeri 1,Network Defense,A,50.00,20.00,70.00,SUBMITTED", content)

    # -------------------------------------------------------------------------
    # Test 23: CSV Export UTF-8 BOM Presence
    # -------------------------------------------------------------------------
    def test_23_csv_export_utf8_bom(self):
        self.login_admin(self.client)
        resp = self.client.get("/admin/results/export.csv")
        self.assertTrue(resp.data.startswith(b"\xef\xbb\xbf"))

    # -------------------------------------------------------------------------
    # Test 24: CSV Formula Injection Prevention
    # -------------------------------------------------------------------------
    def test_24_csv_export_formula_injection_prevention(self):
        self.assertEqual(sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_cell("+cmd"), "'+cmd")
        self.assertEqual(sanitize_csv_cell("-calc"), "'-calc")
        self.assertEqual(sanitize_csv_cell("@test"), "'@test")
        self.assertEqual(sanitize_csv_cell("Normal Text"), "Normal Text")
        self.assertEqual(sanitize_csv_cell(100.5), "100.5")

    # -------------------------------------------------------------------------
    # Test 25: CSV Export Honors Active Filters
    # -------------------------------------------------------------------------
    def test_25_csv_export_honors_filters(self):
        self.login_admin(self.client)
        sess1 = self.create_and_start_session(station_id=self.st1_id, group_id=self.grp_a_id, question_set_id=self.qs1_id)
        sess2 = self.create_and_start_session(station_id=self.st2_id, group_id=self.grp_b_id, question_set_id=self.qs2_id)

        with self.app.app_context():
            sub1 = Submission(session_id=sess1, team_id=self.t_a1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            sub2 = Submission(session_id=sess2, team_id=self.t_b1_id, status=SubmissionStatus.SUBMITTED, current_member=1, started_at=get_server_now())
            db.session.add_all([sub1, sub2])
            db.session.flush()
            db.session.add_all([
                Score(submission_id=sub1.id, raw_score=50.0, time_bonus=20.0, final_score=70.0, submitted_at=get_server_now()),
                Score(submission_id=sub2.id, raw_score=40.0, time_bonus=10.0, final_score=50.0, submitted_at=get_server_now()),
            ])
            db.session.commit()

        # Export for station 1 only
        resp = self.client.get(f"/admin/results/export.csv?station_id={self.st1_id}")
        content = resp.data.decode("utf-8")
        self.assertIn("Alpha Tech", content)
        self.assertNotIn("Delta Sec", content)

    # -------------------------------------------------------------------------
    # Test 26: CSV Export Zero Answer Leakage
    # -------------------------------------------------------------------------
    def test_26_csv_export_zero_answer_leakage(self):
        self.login_admin(self.client)
        self.create_and_start_session()
        resp = self.client.get("/admin/results/export.csv")
        content = resp.data.decode("utf-8")
        self.assertNotIn("correct_answer", content)
        self.assertNotIn("kunci", content.lower())

    # -------------------------------------------------------------------------
    # Test 27: Custom Error Handlers (404 and 403)
    # -------------------------------------------------------------------------
    def test_27_custom_error_handlers_404_and_403(self):
        # 404
        resp404 = self.client.get("/non-existent-page-xyz")
        self.assertEqual(resp404.status_code, 404)
        html404 = resp404.data.decode("utf-8")
        self.assertIn("HALAMAN TIDAK DITEMUKAN", html404)
        self.assertNotIn("Traceback", html404)


if __name__ == "__main__":
    unittest.main()
