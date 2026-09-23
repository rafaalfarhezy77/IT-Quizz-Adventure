"""Operational smoke test using an isolated, in-memory competition database."""
import unittest
from datetime import timedelta
from sqlalchemy.pool import StaticPool

from config import Config
from quiz_app import create_app
from models import (Admin, ChallengePackage, CompetitionSession, Group, PackageStatus,
                    Question, QuestionSet, QuestionSetStatus, SessionStatus, Station,
                    StationMode, SubmissionStatus, Team, db)
from services.quiz_service import get_or_create_submission
from services.scoring_service import finalize_submission
from services.session_service import create_session, finish_session, get_remaining_seconds, get_server_now, start_session
from werkzeug.security import generate_password_hash


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    SECRET_KEY = "admin-ux-smoke"


class AdminJourneyTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            quiz = Station(name="Cyber Security", mode=StationMode.NORMAL)
            hardware = Station(name="Hardware", mode=StationMode.BELUM_DIKETAHUI)
            group = Group(code="A")
            db.session.add_all([quiz, hardware, group, Admin(username="operator", password_hash=generate_password_hash("secret"))])
            db.session.flush()
            self.quiz_id, self.hardware_id, self.group_id = quiz.id, hardware.id, group.id
            for number in range(3):
                db.session.add(Team(team_code=f"A{number}", team_name=f"Tim {number}", school="Sekolah", group_id=group.id))
            question_set = QuestionSet(station_id=quiz.id, code="A", name="Set A", status=QuestionSetStatus.READY)
            db.session.add(question_set)
            db.session.flush()
            self.set_id = question_set.id
            db.session.add(Question(question_set_id=question_set.id, text="Contoh?", option_a="Ya", option_b="Tidak", option_c="C", option_d="D", correct_answer="A", order_number=1))
            db.session.add(ChallengePackage(station_id=hardware.id, package_code="P01", title="Rakit PC", description="Kasus", instructions="Kerjakan", status=PackageStatus.ACTIVE))
            db.session.commit()
        with self.client.session_transaction() as web_session:
            with self.app.app_context():
                web_session["admin_id"] = db.session.scalar(db.select(Admin.id))

    def test_prepare_monitor_refresh_and_close(self):
        with self.app.app_context():
            session_obj = create_session(self.quiz_id, self.group_id, self.set_id, 10)
            session_id = session_obj.id
            self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)
            self.assertEqual(self.client.get(f"/admin/sessions/{session_id}").status_code, 200)
            self.assertTrue(start_session(session_obj)[0])
            started_at = session_obj.started_at
            self.assertFalse(start_session(session_obj)[0])
            self.assertEqual(session_obj.started_at, started_at)
            self.assertGreater(get_remaining_seconds(session_obj), 0)
            self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)
            team_ids = db.session.scalars(db.select(Team.id)).all()
            submissions = [get_or_create_submission(session_id, team_id) for team_id in team_ids]
            self.assertEqual(len({s.id for s in submissions}), 3)
            self.assertEqual(get_or_create_submission(session_id, team_ids[0]).id, submissions[0].id)
            for submission in submissions:
                finalize_submission(submission)
            self.assertTrue(all(s.status == SubmissionStatus.SUBMITTED for s in submissions))
            self.assertEqual(self.client.get(f"/admin/sessions/{session_id}").status_code, 200)
            self.assertEqual(self.client.get(f"/api/admin/sessions/{session_id}/status").json["status"], "RUNNING")
            self.assertTrue(finish_session(session_obj)[0])
            self.assertEqual(self.client.get(f"/api/admin/sessions/{session_id}/status").json["status"], "FINISHED")

    def test_hardware_session_without_question_set_is_visible(self):
        with self.app.app_context():
            response = self.client.post("/admin/sessions/create", data={
                "station_id": self.hardware_id, "group_id": self.group_id,
                "question_set_id": 0, "duration_minutes": 30,
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            session_obj = db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.station_id == self.hardware_id))
            self.assertIsNotNone(session_obj)
            self.assertIsNone(session_obj.question_set)
            self.assertEqual(self.client.get("/admin/sessions").status_code, 200)
            self.assertEqual(self.client.get(f"/admin/sessions/{session_obj.id}").status_code, 200)
            self.assertEqual(self.client.get(f"/admin/sessions/{session_obj.id}/edit").status_code, 200)

    def test_expired_running_session_can_be_closed(self):
        with self.app.app_context():
            session_obj = create_session(self.quiz_id, self.group_id, self.set_id, 1)
            self.assertTrue(start_session(session_obj)[0])
            session_obj.started_at = get_server_now() - timedelta(minutes=2)
            db.session.commit()
            self.assertIn(b"TUTUP SESI YANG WAKTUNYA HABIS", self.client.get(f"/admin/sessions/{session_obj.id}").data)
            self.assertTrue(finish_session(session_obj)[0])
            self.assertEqual(session_obj.status, SessionStatus.FINISHED)


if __name__ == "__main__":
    unittest.main()
