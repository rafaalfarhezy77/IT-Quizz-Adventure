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
from services.quiz_service import (
    advance_member_rotation,
    get_or_create_submission,
    get_session_questions,
    get_submission_answers_map,
    partition_questions_for_members,
    save_answer,
)
from services.scoring_service import (
    calculate_scores,
    finalize_submission,
    get_submission_summary,
)
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
    SECRET_KEY = "test-key-step7"
    TIME_BONUS_PER_SECOND = 1.0
    MEMBER_ROTATION_COUNT = 3


class Step7QuizSubmissionScoringTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Seed Admin
            admin = Admin(username="root_admin", password_hash=generate_password_hash("AdminSecret123!"), is_active=True)
            db.session.add(admin)

            # Seed Stations
            st_norm = Station(name="Network Defense", mode=StationMode.NORMAL, is_active=True)
            st_rot = Station(name="Software Engineering", mode=StationMode.MEMBER_ROTATION, is_active=True)
            db.session.add_all([st_norm, st_rot])
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
            # Set A for Station NORMAL (READY)
            qs_norm = QuestionSet(station_id=st_norm.id, code="A", name="NetSec Set A", status=QuestionSetStatus.READY)
            # Set A for Station ROTATION (READY)
            qs_rot = QuestionSet(station_id=st_rot.id, code="A", name="SoftEng Set A", status=QuestionSetStatus.READY)
            # Other question set (Set B) for Station NORMAL
            qs_other = QuestionSet(station_id=st_norm.id, code="B", name="NetSec Set B", status=QuestionSetStatus.READY)
            db.session.add_all([qs_norm, qs_rot, qs_other])
            db.session.flush()

            # Add 4 questions to qs_norm (weights: 25, 25, 30, 20 = 100 total)
            q_n1 = Question(
                question_set_id=qs_norm.id,
                text="Apa protokol default untuk browsing web yang aman?",
                option_a="HTTP",
                option_b="HTTPS",
                option_c="FTP",
                option_d="SSH",
                correct_answer="B",
                weight=25.0,
                order_number=1,
                is_active=True,
            )
            q_n2 = Question(
                question_set_id=qs_norm.id,
                text="Berapakah port standar untuk DNS?",
                option_a="53",
                option_b="80",
                option_c="443",
                option_d="22",
                correct_answer="A",
                weight=25.0,
                order_number=2,
                is_active=True,
            )
            q_n3 = Question(
                question_set_id=qs_norm.id,
                text="Metode enkripsi asimetris yang populer adalah...",
                option_a="AES",
                option_b="DES",
                option_c="RSA",
                option_d="RC4",
                correct_answer="C",
                weight=30.0,
                order_number=3,
                is_active=True,
            )
            q_n4 = Question(
                question_set_id=qs_norm.id,
                text="Manakah yang merupakan private IP range?",
                option_a="8.8.8.8",
                option_b="1.1.1.1",
                option_c="192.168.1.1",
                option_d="172.33.0.1",
                correct_answer="C",
                weight=20.0,
                order_number=4,
                is_active=True,
            )
            # Add an inactive question to qs_norm to verify exclusion
            q_n_inactive = Question(
                question_set_id=qs_norm.id,
                text="Soal nonaktif yang tidak boleh muncul",
                option_a="A",
                option_b="B",
                option_c="C",
                option_d="D",
                correct_answer="A",
                weight=10.0,
                order_number=5,
                is_active=False,
            )

            # Add 6 questions to qs_rot for 3 members (2 questions per member)
            q_r1 = Question(question_set_id=qs_rot.id, text="SE Soal 1", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="A", weight=10.0, order_number=1, is_active=True)
            q_r2 = Question(question_set_id=qs_rot.id, text="SE Soal 2", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="B", weight=10.0, order_number=2, is_active=True)
            q_r3 = Question(question_set_id=qs_rot.id, text="SE Soal 3", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="C", weight=15.0, order_number=3, is_active=True)
            q_r4 = Question(question_set_id=qs_rot.id, text="SE Soal 4", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="D", weight=15.0, order_number=4, is_active=True)
            q_r5 = Question(question_set_id=qs_rot.id, text="SE Soal 5", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="A", weight=25.0, order_number=5, is_active=True)
            q_r6 = Question(question_set_id=qs_rot.id, text="SE Soal 6", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="B", weight=25.0, order_number=6, is_active=True)

            # Add 1 question to qs_other
            q_other = Question(question_set_id=qs_other.id, text="Other Set Question", option_a="A", option_b="B", option_c="C", option_d="D", correct_answer="A", weight=50.0, order_number=1, is_active=True)

            db.session.add_all([q_n1, q_n2, q_n3, q_n4, q_n_inactive, q_r1, q_r2, q_r3, q_r4, q_r5, q_r6, q_other])
            db.session.commit()

            self.st_norm_id = st_norm.id
            self.st_rot_id = st_rot.id
            self.grp_a_id = grp_a.id
            self.grp_b_id = grp_b.id
            self.t_a1_id = t_a1.id
            self.t_a2_id = t_a2.id
            self.t_b1_id = t_b1.id
            self.qs_norm_id = qs_norm.id
            self.qs_rot_id = qs_rot.id
            self.qs_other_id = qs_other.id

            self.q_n1_id = q_n1.id
            self.q_n2_id = q_n2.id
            self.q_n3_id = q_n3.id
            self.q_n4_id = q_n4.id
            self.q_n_inactive_id = q_n_inactive.id

            self.q_r1_id = q_r1.id
            self.q_r2_id = q_r2.id
            self.q_r3_id = q_r3.id
            self.q_r4_id = q_r4.id
            self.q_r5_id = q_r5.id
            self.q_r6_id = q_r6.id
            self.q_other_id = q_other.id

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

    def setup_participant(self, client, station_id=None, group_id=None, team_id=None):
        st_id = station_id or self.st_norm_id
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

    def create_and_start_session(self, station_id=None, group_id=None, question_set_id=None, duration_minutes=10):
        st_id = station_id or self.st_norm_id
        g_id = group_id or self.grp_a_id
        qs_id = question_set_id or self.qs_norm_id

        with self.app.app_context():
            from services.session_service import create_session, start_session
            sess = create_session(st_id, g_id, qs_id, duration_minutes)
            start_session(sess)
            return sess.id

    # -------------------------------------------------------------------------
    # Test 1: Stage protection on /participant/quiz
    # -------------------------------------------------------------------------
    def test_01_quiz_route_stage_protection_unauthorized(self):
        resp = self.client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/access", resp.headers["Location"])

    # -------------------------------------------------------------------------
    # Test 2: Session WAITING redirects to /participant/waiting
    # -------------------------------------------------------------------------
    def test_02_quiz_route_session_waiting_redirects_waiting(self):
        with self.app.app_context():
            from services.session_service import create_session
            create_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)

        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)
        resp = self.client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/waiting", resp.headers["Location"])

    # -------------------------------------------------------------------------
    # Test 3: Session CANCELLED redirects to /participant/waiting
    # -------------------------------------------------------------------------
    def test_03_quiz_route_session_cancelled_redirects_waiting(self):
        with self.app.app_context():
            from services.session_service import cancel_session, create_session
            sess = create_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
            cancel_session(sess)

        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)
        resp = self.client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/waiting", resp.headers["Location"])

    # -------------------------------------------------------------------------
    # Test 4: RUNNING session creates Submission and displays quiz
    # -------------------------------------------------------------------------
    def test_04_quiz_route_session_running_creates_submission(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        resp = self.client.get("/participant/quiz")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Network Defense", html)
        self.assertIn("Alpha Tech", html)
        self.assertIn("Apa protokol default untuk browsing web yang aman?", html)

        with self.app.app_context():
            sub = db.session.scalar(
                db.select(Submission).where(
                    Submission.session_id == sess_id,
                    Submission.team_id == self.t_a1_id,
                )
            )
            self.assertIsNotNone(sub)
            self.assertEqual(sub.status, SubmissionStatus.IN_PROGRESS)
            self.assertEqual(sub.current_member, 1)
            self.assertIsNotNone(sub.started_at)

    # -------------------------------------------------------------------------
    # Test 5: Idempotent Submission creation (no duplicates on refresh)
    # -------------------------------------------------------------------------
    def test_05_quiz_route_get_or_create_submission_idempotent(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        # Visit 3 times
        self.client.get("/participant/quiz")
        self.client.get("/participant/quiz")
        self.client.get("/participant/quiz")

        with self.app.app_context():
            subs = db.session.scalars(
                db.select(Submission).where(
                    Submission.session_id == sess_id,
                    Submission.team_id == self.t_a1_id,
                )
            ).all()
            self.assertEqual(len(subs), 1)

    # -------------------------------------------------------------------------
    # Test 6: Zero Answer Key Leakage
    # -------------------------------------------------------------------------
    def test_06_quiz_zero_leakage_of_correct_answer_and_weights(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        resp = self.client.get("/participant/quiz")
        html = resp.data.decode("utf-8")

        # 1. correct_answer string must not appear as attribute or JS variable
        self.assertNotIn("correct_answer", html)
        self.assertNotIn("data-correct", html)
        self.assertNotIn("kunci_jawaban", html)
        # 2. Specific correct answers tied to question IDs must not appear in JSON configs
        self.assertNotIn('"correct":', html)
        self.assertNotIn('"answer":', html)

    # -------------------------------------------------------------------------
    # Test 7: Question Set Isolation & Active Questions Only
    # -------------------------------------------------------------------------
    def test_07_question_set_isolation(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        resp = self.client.get("/participant/quiz")
        html = resp.data.decode("utf-8")

        # Active questions from NetSec Set A must be present
        self.assertIn("Apa protokol default untuk browsing web yang aman?", html)
        self.assertIn("Berapakah port standar untuk DNS?", html)
        self.assertIn("Metode enkripsi asimetris yang populer adalah...", html)
        self.assertIn("Manakah yang merupakan private IP range?", html)

        # Inactive question must NOT be present
        self.assertNotIn("Soal nonaktif yang tidak boleh muncul", html)

        # Questions from other set or station must NOT be present
        self.assertNotIn("Other Set Question", html)
        self.assertNotIn("SE Soal 1", html)

    # -------------------------------------------------------------------------
    # Test 8: Autosave Answer via API Success
    # -------------------------------------------------------------------------
    def test_08_api_save_answer_success(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        # Load quiz to get CSRF token
        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "B"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["saved"])
        self.assertEqual(data["question_id"], self.q_n1_id)
        self.assertEqual(data["selected_answer"], "B")
        self.assertEqual(data["answered_count"], 1)

        # Verify in DB
        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            ans = db.session.scalar(db.select(Answer).where(Answer.submission_id == sub.id, Answer.question_id == self.q_n1_id))
            self.assertIsNotNone(ans)
            self.assertEqual(ans.selected_answer, "B")

    # -------------------------------------------------------------------------
    # Test 9: Autosave Answer Upsert (replaces existing answer without duplicates)
    # -------------------------------------------------------------------------
    def test_09_api_save_answer_upsert(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Save 'A'
        self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "A"},
        )

        # Change to 'B'
        resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "B"},
        )
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            answers = db.session.scalars(db.select(Answer).where(Answer.submission_id == sub.id, Answer.question_id == self.q_n1_id)).all()
            self.assertEqual(len(answers), 1)
            self.assertEqual(answers[0].selected_answer, "B")

    # -------------------------------------------------------------------------
    # Test 10: Invalid options rejected (only A, B, C, D allowed)
    # -------------------------------------------------------------------------
    def test_10_api_save_answer_invalid_options_rejected(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        for invalid_opt in ["E", "1", "TRUE", ""]:
            resp = self.client.post(
                "/api/participant/answer",
                headers={"X-CSRFToken": token, "Content-Type": "application/json"},
                json={"question_id": self.q_n1_id, "selected_answer": invalid_opt},
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("error", resp.get_json())

    # -------------------------------------------------------------------------
    # Test 11: Invalid or foreign question_id rejected
    # -------------------------------------------------------------------------
    def test_11_api_save_answer_invalid_question_id(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Question from another set (qs_other)
        resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_other_id, "selected_answer": "A"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("tidak termasuk dalam paket soal", resp.get_json()["error"])

        # Non-existent question ID
        resp2 = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": 99999, "selected_answer": "A"},
        )
        self.assertEqual(resp2.status_code, 400)

    # -------------------------------------------------------------------------
    # Test 12: Inactive / soft-deleted question rejected
    # -------------------------------------------------------------------------
    def test_12_api_save_answer_inactive_question_rejected(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n_inactive_id, "selected_answer": "A"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("dinonaktifkan", resp.get_json()["error"])

    # -------------------------------------------------------------------------
    # Test 13: CSRF Protection on API
    # -------------------------------------------------------------------------
    def test_13_api_save_answer_csrf_protection(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        # POST without CSRF header
        resp = self.client.post(
            "/api/participant/answer",
            headers={"Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "B"},
        )
        self.assertEqual(resp.status_code, 400)

    # -------------------------------------------------------------------------
    # Test 14: Rejection of answers after submission is finalized
    # -------------------------------------------------------------------------
    def test_14_api_save_answer_after_finalized_rejected(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Finalize submission directly in DB
        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            sub.status = SubmissionStatus.SUBMITTED
            db.session.commit()

        resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "B"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("telah difinalisasi", resp.get_json()["error"])

    # -------------------------------------------------------------------------
    # Test 15: Rejection of answers when session timer expired
    # -------------------------------------------------------------------------
    def test_15_api_save_answer_after_deadline_expired_rejected(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Advance session start time into the past (expired)
        with self.app.app_context():
            sess = db.session.get(CompetitionSession, sess_id)
            sess.started_at = get_server_now() - timedelta(seconds=700)  # duration is 600s
            db.session.commit()

        resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "B"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(resp.get_json().get("status"), ("TIMED_OUT", "FINISHED"))

    # -------------------------------------------------------------------------
    # Test 16: Quiz refresh retains saved answers in UI
    # -------------------------------------------------------------------------
    def test_16_quiz_refresh_retains_saved_answers(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Answer question 1 with B and question 2 with A
        self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n1_id, "selected_answer": "B"},
        )
        self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_n2_id, "selected_answer": "A"},
        )

        # Refresh GET /participant/quiz
        resp = self.client.get("/participant/quiz")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")

        # Verify radio buttons have checked attributes matching saved answers
        self.assertRegex(html, rf'name=["\']question_{self.q_n1_id}["\'][^>]*value=["\']B["\'][^>]*checked')
        self.assertRegex(html, rf'name=["\']question_{self.q_n2_id}["\'][^>]*value=["\']A["\'][^>]*checked')
        # Question 3 was not answered, so none of its options should be checked
        self.assertNotRegex(html, rf'name=["\']question_{self.q_n3_id}["\'][^>]*checked')

    # -------------------------------------------------------------------------
    # Test 17: Deterministic partitioning helper (Unit Test)
    # -------------------------------------------------------------------------
    def test_17_member_rotation_partition_deterministic(self):
        with self.app.app_context():
            # 6 questions, 3 members -> 2, 2, 2
            questions_6 = db.session.scalars(
                db.select(Question).where(Question.question_set_id == self.qs_rot_id).order_by(Question.order_number)
            ).all()
            part6 = partition_questions_for_members(questions_6, 3)
            self.assertEqual(len(part6[1]), 2)
            self.assertEqual(len(part6[2]), 2)
            self.assertEqual(len(part6[3]), 2)
            # Ensure total matches and no overlaps
            all_ids = [q.id for member_qs in part6.values() for q in member_qs]
            self.assertEqual(len(all_ids), 6)
            self.assertEqual(len(set(all_ids)), 6)

            # Test uneven count: 7 questions, 3 members -> 3, 2, 2
            dummy_qs = [Question(text=f"Q{i}", order_number=i) for i in range(1, 8)]
            part7 = partition_questions_for_members(dummy_qs, 3)
            self.assertEqual(len(part7[1]), 3)
            self.assertEqual(len(part7[2]), 2)
            self.assertEqual(len(part7[3]), 2)
            self.assertEqual(sum(len(v) for v in part7.values()), 7)

    # -------------------------------------------------------------------------
    # Test 18: Member Rotation: Question Isolation by Member
    # -------------------------------------------------------------------------
    def test_18_member_rotation_flow_and_isolation(self):
        self.create_and_start_session(self.st_rot_id, self.grp_a_id, self.qs_rot_id, 10)
        self.setup_participant(self.client, self.st_rot_id, self.grp_a_id, self.t_a1_id)

        resp = self.client.get("/participant/quiz")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")

        # Member 1 should see SE Soal 1 and SE Soal 2
        self.assertIn("SE Soal 1", html)
        self.assertIn("SE Soal 2", html)
        # But NOT Member 2's or Member 3's questions
        self.assertNotIn("SE Soal 3", html)
        self.assertNotIn("SE Soal 5", html)

        # Attempting to save an answer for Member 2's question (q_r3) as Member 1 must be rejected
        token = self.extract_csrf_token(html)
        err_resp = self.client.post(
            "/api/participant/answer",
            headers={"X-CSRFToken": token, "Content-Type": "application/json"},
            json={"question_id": self.q_r3_id, "selected_answer": "C"},
        )
        self.assertEqual(err_resp.status_code, 400)
        self.assertIn("bukan merupakan bagian dari giliran Anggota 1", err_resp.get_json()["error"])

    # -------------------------------------------------------------------------
    # Test 19: Member Transition Screen after member submit
    # -------------------------------------------------------------------------
    def test_19_member_rotation_transition_screen(self):
        sess_id = self.create_and_start_session(self.st_rot_id, self.grp_a_id, self.qs_rot_id, 10)
        self.setup_participant(self.client, self.st_rot_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Member 1 saves their questions
        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_r1_id, "selected_answer": "A"})
        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_r2_id, "selected_answer": "B"})

        # Member 1 submits section
        resp = self.client.post("/participant/quiz/member-submit", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/quiz/member-transition", resp.headers["Location"])

        # Follow to transition screen
        t_page = self.client.get("/participant/quiz/member-transition")
        self.assertEqual(t_page.status_code, 200)
        t_html = t_page.data.decode("utf-8")
        self.assertIn("SILAKAN GANTI GILIRAN ANGGOTA", t_html)
        self.assertIn("Anggota 1", t_html)
        self.assertIn("Anggota 2", t_html)

        # In DB, current_member should now be 2
        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            self.assertEqual(sub.current_member, 2)
            self.assertEqual(sub.status, SubmissionStatus.IN_PROGRESS)

        # Now when Member 2 visits /participant/quiz, they see SE Soal 3 and SE Soal 4
        m2_page = self.client.get("/participant/quiz")
        m2_html = m2_page.data.decode("utf-8")
        self.assertIn("SE Soal 3", m2_html)
        self.assertIn("SE Soal 4", m2_html)
        self.assertNotIn("SE Soal 1", m2_html)

    # -------------------------------------------------------------------------
    # Test 20: Final Member Submits Section -> Submission Finalized
    # -------------------------------------------------------------------------
    def test_20_member_rotation_final_member_submits_finalizes(self):
        sess_id = self.create_and_start_session(self.st_rot_id, self.grp_a_id, self.qs_rot_id, 10)
        self.setup_participant(self.client, self.st_rot_id, self.grp_a_id, self.t_a1_id)

        # Fast forward current_member to 3 (final member)
        with self.app.app_context():
            sub = get_or_create_submission(sess_id, self.t_a1_id)
            sub.current_member = 3
            db.session.commit()

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Final member submits
        resp = self.client.post("/participant/quiz/member-submit", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/result", resp.headers["Location"])

        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            self.assertEqual(sub.status, SubmissionStatus.SUBMITTED)
            self.assertIsNotNone(sub.score)

    # -------------------------------------------------------------------------
    # Test 21: Final Submit: Raw Score & Time Bonus Calculation
    # -------------------------------------------------------------------------
    def test_21_final_submit_scoring_raw_and_time_bonus(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # NetSec Set A weights:
        # q_n1: 25.0 (correct: B) -> answer B (Correct +25)
        # q_n2: 25.0 (correct: A) -> answer A (Correct +25)
        # q_n3: 30.0 (correct: C) -> answer D (Incorrect 0)
        # q_n4: 20.0 (correct: C) -> leave unanswered (0)
        # Expected Raw Score: 25 + 25 = 50.0

        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_n1_id, "selected_answer": "B"})
        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_n2_id, "selected_answer": "A"})
        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_n3_id, "selected_answer": "D"})

        # Submit final
        resp = self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/result", resp.headers["Location"])

        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            self.assertEqual(sub.status, SubmissionStatus.SUBMITTED)
            score = sub.score
            self.assertIsNotNone(score)
            self.assertEqual(score.raw_score, 50.0)
            # Duration is 600s, submitting immediately leaves ~599-600s remaining.
            # Bonus is 1.0 per second.
            self.assertGreater(score.time_bonus, 580.0)
            self.assertEqual(score.final_score, round(score.raw_score + score.time_bonus, 2))

    # -------------------------------------------------------------------------
    # Test 22: Unanswered questions allowed with 0 points
    # -------------------------------------------------------------------------
    def test_22_final_submit_unanswered_questions_awarded_zero(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Submit without answering anything
        resp = self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            self.assertEqual(sub.score.raw_score, 0.0)
            self.assertGreater(sub.score.final_score, 0.0)  # Got time bonus

    # -------------------------------------------------------------------------
    # Test 23: Double submit protection (Idempotency)
    # -------------------------------------------------------------------------
    def test_23_final_submit_double_submit_protection_idempotency(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_n1_id, "selected_answer": "B"})

        # Submit 1
        resp1 = self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(resp1.status_code, 302)

        with self.app.app_context():
            score1 = db.session.scalar(db.select(Score).join(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            initial_score_val = score1.final_score
            initial_sub_time = score1.submitted_at

        # Submit 2 (simulating double click)
        resp2 = self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(resp2.status_code, 302)

        with self.app.app_context():
            scores = db.session.scalars(db.select(Score).join(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id)).all()
            self.assertEqual(len(scores), 1)
            self.assertEqual(scores[0].final_score, initial_score_val)
            self.assertEqual(scores[0].submitted_at, initial_sub_time)

    # -------------------------------------------------------------------------
    # Test 24: Auto-timeout finalization: Zero time bonus
    # -------------------------------------------------------------------------
    def test_24_auto_timeout_finalization_zero_time_bonus(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Answer question 1 correctly (+25)
        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_n1_id, "selected_answer": "B"})

        # Expire session timer
        with self.app.app_context():
            sess = db.session.get(CompetitionSession, sess_id)
            sess.started_at = get_server_now() - timedelta(seconds=650)
            db.session.commit()

        # Accessing /participant/quiz should auto-finalize as TIMED_OUT and redirect to result
        resp = self.client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/result", resp.headers["Location"])

        with self.app.app_context():
            sub = db.session.scalar(db.select(Submission).where(Submission.session_id == sess_id, Submission.team_id == self.t_a1_id))
            self.assertEqual(sub.status, SubmissionStatus.TIMED_OUT)
            self.assertEqual(sub.score.raw_score, 25.0)
            self.assertEqual(sub.score.time_bonus, 0.0)
            self.assertEqual(sub.score.final_score, 25.0)

    # -------------------------------------------------------------------------
    # Test 25: Result page summary without answer key leakage
    # -------------------------------------------------------------------------
    def test_25_result_page_shows_summary_without_leakage(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        self.client.post("/api/participant/answer", headers={"X-CSRFToken": token, "Content-Type": "application/json"}, json={"question_id": self.q_n1_id, "selected_answer": "B"})
        self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=True)

        res_page = self.client.get("/participant/result")
        self.assertEqual(res_page.status_code, 200)
        html = res_page.data.decode("utf-8")

        # Must display team and score stats
        self.assertIn("Alpha Tech", html)
        self.assertIn("HASIL PENILAIAN POS", html)
        self.assertIn("TOTAL SKOR AKHIR", html)
        self.assertIn("NILAI MURNI", html)
        self.assertIn("BONUS SISA WAKTU", html)

        # Must NEVER leak answers or question review
        self.assertNotIn("correct_answer", html)
        self.assertNotIn("data-correct", html)
        self.assertNotIn("Apa protokol default", html)
        self.assertNotIn("Berapakah port standar", html)

    # -------------------------------------------------------------------------
    # Test 26: Submitting redirects subsequent /participant/quiz to /participant/result
    # -------------------------------------------------------------------------
    def test_26_quiz_page_redirects_to_result_after_submission(self):
        self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)
        self.setup_participant(self.client, self.st_norm_id, self.grp_a_id, self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=True)

        # Subsequent visit to /participant/quiz
        resp = self.client.get("/participant/quiz", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/participant/result", resp.headers["Location"])

    # -------------------------------------------------------------------------
    # Test 27: Summary helper unit test
    # -------------------------------------------------------------------------
    def test_27_get_submission_summary_helper(self):
        sess_id = self.create_and_start_session(self.st_norm_id, self.grp_a_id, self.qs_norm_id, 10)

        with self.app.app_context():
            sub = get_or_create_submission(sess_id, self.t_a1_id)
            save_answer(sub, self.q_n1_id, "B")  # correct
            save_answer(sub, self.q_n2_id, "D")  # incorrect
            finalize_submission(sub, is_timeout=False)

            summary = get_submission_summary(sub)
            self.assertEqual(summary["total_questions"], 4)
            self.assertEqual(summary["answered_count"], 2)
            self.assertEqual(summary["unanswered_count"], 2)
            self.assertEqual(summary["correct_count"], 1)
            self.assertEqual(summary["raw_score"], 25.0)
            self.assertEqual(summary["team_code"], "A-01")


if __name__ == "__main__":
    unittest.main()
