"""Leaderboard regression checks with an isolated in-memory database."""
import unittest
from datetime import timedelta
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from models import (db, Admin, Group, Team, Station, CompetitionSession, Submission,
                    Score, HardwareSubmission, NetworkingSubmission, SessionStatus,
                    SubmissionStatus, utcnow)
from routes.admin import admin_bp
from routes.api import api_bp
from services.leaderboard_service import get_global_leaderboard


class GlobalLeaderboardTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="templates")
        self.app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://",
                               WTF_CSRF_ENABLED=False)
        db.init_app(self.app)
        CSRFProtect(self.app)
        self.app.register_blueprint(admin_bp)
        self.app.register_blueprint(api_bp)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.admin = Admin(username="test", password_hash="test")
        self.group = Group(code="A")
        self.stations = [Station(name=name) for name in ["Software Engineering", "Cyber Security", "Hardware", "Networking"]]
        db.session.add_all([self.admin, self.group, *self.stations])
        db.session.flush()
        self.teams = [Team(team_code=f"T{i}", team_name=f"Tim {i}", school="Sekolah", group=self.group) for i in range(4)]
        self.teams[-1].is_active = False
        db.session.add_all(self.teams)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(admin_id=self.admin.id, admin_station_id=0)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def result(self, team, station, points, age=0, specialized=None, cancelled=False, status=SubmissionStatus.GRADED):
        competition = CompetitionSession(station=station, group=self.group, duration_seconds=600,
                                          status=SessionStatus.CANCELLED if cancelled else SessionStatus.FINISHED)
        submission = Submission(team=team, session=competition, status=status)
        db.session.add(submission)
        db.session.flush()
        db.session.add(Score(submission=submission, final_score=points, submitted_at=utcnow() - timedelta(seconds=age)))
        if station.name == "Hardware":
            db.session.add(HardwareSubmission(submission=submission, verification_status=specialized or "SUBMITTED"))
        if station.name == "Networking":
            db.session.add(NetworkingSubmission(submission=submission, verification_status=specialized or "VERIFIED"))
        db.session.commit()
        return submission

    def test_latest_official_totals_and_ties(self):
        first, second, zero, inactive = self.teams
        software, cyber, hardware, networking = self.stations
        self.result(first, software, 100, age=100)
        self.result(first, software, 20, age=50)
        self.result(first, software, 900, cancelled=True)
        self.result(first, software, 999, status=SubmissionStatus.IN_PROGRESS)
        self.result(first, cyber, 10)
        self.result(first, hardware, 15, age=60, specialized="VERIFIED")
        self.result(first, hardware, 800, specialized="NEEDS_REVIEW")
        self.result(first, networking, 5, specialized="FINALIZED")
        self.result(second, software, 50)
        self.result(second, networking, 999, specialized="VERIFIED")
        self.result(inactive, software, 1000)
        payload = get_global_leaderboard()
        self.assertEqual([row["total"] for row in payload["rows"]], [50, 50, 0])
        self.assertEqual([row["rank"] for row in payload["rows"]], [1, 1, 3])
        self.assertEqual(payload["rows"][0]["points"][str(software.id)], 20)
        self.assertIsNone(payload["rows"][2]["points"][str(hardware.id)])

    def test_api_live_changes_and_authorization(self):
        endpoint = "/api/admin/global-leaderboard"
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        sub = self.result(self.teams[1], self.stations[0], 30)
        self.assertEqual(self.client.get(endpoint).json["rows"][0]["team_id"], self.teams[1].id)
        sub.score.final_score = 10
        self.result(self.teams[0], self.stations[1], 20)
        self.assertEqual(self.client.get(endpoint).json["rows"][0]["team_id"], self.teams[0].id)
        self.teams[0].is_active = False
        db.session.delete(self.teams[2])
        db.session.commit()
        self.assertEqual(len(self.client.get(endpoint).json["rows"]), 1)
        self.admin.is_active = False
        db.session.commit()
        self.assertEqual(self.client.get(endpoint).status_code, 401)
        self.assertEqual(self.app.test_client().get(endpoint).status_code, 401)

    def test_views_and_empty_state(self):
        page = self.client.get("/admin/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"data-leaderboard", page.data)
        with self.client.session_transaction() as session:
            session["admin_station_id"] = self.stations[0].id
        self.assertNotIn(b"data-leaderboard", self.client.get("/admin/dashboard").data)
        page = self.client.get("/admin/leaderboard/global/display")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"data-fullscreen", page.data)
        self.assertNotIn(b'<aside class="sidebar"', page.data)
        self.assertEqual(self.app.test_client().get("/admin/leaderboard/global/display").status_code, 302)
        for team in self.teams:
            team.is_active = False
        db.session.commit()
        self.assertEqual(get_global_leaderboard()["rows"], [])


if __name__ == "__main__":
    unittest.main()
