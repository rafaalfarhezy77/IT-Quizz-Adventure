"""Practice isolation and lifecycle regression; uses temporary SQLite files."""
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text
from config import Config
from models import (db, Station, StationMode, Group, Team, QuestionSet, QuestionSetStatus,
                    Question, CompetitionSession, SessionStatus, Submission, SubmissionStatus, Score, utcnow)
from services.leaderboard_service import get_global_leaderboard, generate_results_csv, get_filtered_results
from quiz_app import create_app
from services import demo_service as store
from services.demo_questions import load_pack


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "demo-test-only"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + (root / "official.db").as_posix()
            DEMO_DATABASE_PATH = str(root / "demo.db")
            UPLOAD_FOLDER = str(root / "uploads")
            DEMO_ENABLED = True
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            station = Station(name="Software Engineering", mode=StationMode.MEMBER_ROTATION)
            group = Group(code="A")
            team = Team(team_code="A01", team_name="Official team", school="School", group=group)
            questions = QuestionSet(name="Official set", code="A", station=station, status=QuestionSetStatus.READY)
            question = Question(question_set=questions, text="Official question", correct_answer="D", weight=10,
                                order_number=1, option_a="A", option_b="B", option_c="C", option_d="D")
            competition = CompetitionSession(station=station, group=group, question_set=questions,
                                             status=SessionStatus.FINISHED, duration_seconds=600)
            submission = Submission(session=competition, team=team, status=SubmissionStatus.SUBMITTED)
            score = Score(submission=submission, raw_score=10, time_bonus=0, final_score=10, submitted_at=utcnow())
            db.session.add_all([station, group, team, questions, question, competition, submission, score])
            db.session.commit()
            self.official_ids = (station.id, group.id, team.id)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.tmp.cleanup()

    def csrf(self, client=None):
        page = (client or self.client).get("/demo/software/rules")
        self.assertEqual(page.status_code, 200)
        return re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()

    def start(self, client=None):
        client = client or self.client
        token = self.csrf(client)
        response = client.post("/demo/software/start", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        identifier = response.location.split("/")[2]
        client.post(response.location, data={"csrf_token": token})
        return identifier, token

    def read(self, identifier, client=None):
        with (client or self.client).session_transaction() as s:
            owner = s["demo_owner"]
        with self.app.app_context():
            return store.access_attempt(identifier, owner)

    def answer(self, identifier, token, member, answers, client=None):
        return (client or self.client).post(f"/demo/{identifier}/answer", json={"member": member, "answers": answers, "revision": self.read(identifier)["revision"]},
                                          headers={"X-CSRFToken": token})

    def finish(self, identifier, token):
        for member in (1, 2):
            response = self.client.post(f"/demo/{identifier}/advance", data={"csrf_token": token, "member": member, "revision": self.read(identifier)["revision"],
                                                                         f"question_{(member-1)*3+1}": "A"})
            self.assertEqual(response.status_code, 200)
        return self.client.post(f"/demo/{identifier}/submit", data={"csrf_token": token, "member": 3, "question_9": "A", "revision": self.read(identifier)["revision"]})

    def official_snapshot(self):
        with self.app.app_context(), db.engine.connect() as conn:
            tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars().all()
            return {name: list(conn.execute(text(f'SELECT * FROM "{name}"')).all()) for name in tables}

    def test_full_flow_and_no_keys_before_finish(self):
        self.assertIn(b"Coba Demo", self.client.get("/").data)
        self.assertIn(b"/demo/hardware/rules", self.client.get("/demo/").data)
        identifier, token = self.start()
        page = self.client.get(f"/demo/{identifier}/quiz")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Mode Demo", page.data)
        self.assertIn(b"demo_timer.js", page.data)
        self.assertNotIn(b"correct_answer", page.data)
        self.assertNotIn(b"explanation", page.data)
        for question in load_pack()["questions"]:
            self.assertNotIn(question["explanation"].encode(), page.data)
        self.assertEqual(self.finish(identifier, token).status_code, 302)
        result = self.client.get(f"/demo/{identifier}/result")
        self.assertIn(b"Jawaban benar", result.data)
        self.assertIn(b"Coba Lagi", result.data)
        self.assertEqual(self.read(identifier)["result"]["raw_score"], 20.0)

    def test_two_browsers_and_ownership(self):
        first, token = self.start()
        other = self.app.test_client()
        second, other_token = self.start(other)
        self.assertNotEqual(first, second)
        self.assertEqual(other.get(f"/demo/{first}/quiz").status_code, 404)
        self.assertEqual(self.answer(first, other_token, 1, {"1": "B"}, other).status_code, 404)
        self.answer(first, token, 1, {"1": "A"})
        self.assertEqual(self.read(second, other)["answers"], {})

    def test_refresh_preserves_deadline_and_answers(self):
        identifier, token = self.start()
        original = self.read(identifier)
        self.assertEqual(self.answer(identifier, token, 1, {"1": "C"}).status_code, 200)
        page = self.client.get(f"/demo/{identifier}/quiz")
        self.assertIn(b"checked", page.data)
        current = self.read(identifier)
        self.assertEqual(current["deadline"], original["deadline"])
        self.assertEqual(current["answers"], {"1": "C"})
        # A second application/worker reads the same store, with no globals.
        with self.app.app_context():
            self.assertEqual(store.access_attempt(identifier, original["owner"])["answers"], {"1": "C"})

    def test_retry_is_new_attempt_without_changing_old(self):
        identifier, token = self.start()
        self.finish(identifier, token)
        before = self.read(identifier)
        new, _ = self.start()
        self.assertNotEqual(identifier, new)
        self.assertEqual(before, self.read(identifier))

    def test_double_submit_and_locked_answers(self):
        identifier, token = self.start()
        self.finish(identifier, token)
        original = self.read(identifier)
        self.client.post(f"/demo/{identifier}/submit", data={"csrf_token": token, "member": 3, "question_9": "D"})
        self.assertEqual(self.read(identifier), original)
        self.assertEqual(self.answer(identifier, token, 3, {"9": "D"}).status_code, 409)

    def test_timeout_finalizes_saved_answers_and_rejects_late_changes(self):
        identifier, token = self.start()
        self.answer(identifier, token, 1, {"1": "A"})
        deadline = self.read(identifier)["deadline"]
        with patch.object(store, "now", return_value=deadline + 1):
            self.assertEqual(self.answer(identifier, token, 1, {"1": "B"}).status_code, 409)
            a = self.read(identifier)
            self.assertEqual(a["status"], "TIMED_OUT")
            self.assertEqual(a["result"]["raw_score"], 10)
            self.assertEqual(a["result"]["time_bonus"], 0)
            self.assertIn(b"Waktu habis", self.client.get(f"/demo/{identifier}/result").data)

    def test_expiry_and_cleanup(self):
        identifier, _ = self.start()
        expiry = self.read(identifier)["expires"]
        with patch.object(store, "now", return_value=expiry + 1):
            self.assertEqual(self.client.get(f"/demo/{identifier}/result").status_code, 410)
            with self.app.app_context():
                self.assertEqual(store.cleanup(), 1)
        self.assertEqual(self.client.get(f"/demo/{identifier}/quiz").status_code, 404)

    def test_rotations_validate_member_and_lock_previous(self):
        identifier, token = self.start()
        self.assertEqual(self.answer(identifier, token, 1, {"4": "A"}).status_code, 400)
        self.assertEqual(self.client.post(f"/demo/{identifier}/submit", data={"csrf_token": token, "member": 1}).status_code, 409)
        self.assertEqual(self.client.post(f"/demo/{identifier}/advance", data={"csrf_token": token, "member": 1, "revision": self.read(identifier)["revision"]}).status_code, 200)
        self.assertEqual(self.client.post(f"/demo/{identifier}/advance", data={"csrf_token": token, "member": 1}).status_code, 409)
        self.assertEqual(self.answer(identifier, token, 1, {"1": "A"}).status_code, 409)

    def test_competition_unchanged_and_official_endpoints_reject_demo(self):
        before = self.official_snapshot()
        with self.app.app_context():
            leaderboard_before = get_global_leaderboard()
            export_before = generate_results_csv(get_filtered_results())
        identifier, token = self.start()
        with self.client.session_transaction() as s:
            s.update(participant_authorized=True, participant_station_id=self.official_ids[0],
                     participant_group_id=self.official_ids[1], participant_team_id=self.official_ids[2],
                     participant_confirmed=True, participant_rules_accepted=True)
        for path in ("/api/participant/answer", "/participant/quiz/submit", "/participant/quiz/member-submit"):
            response = self.client.post(path, json={"mode": "demo", "session_id": identifier, "question_id": 1,
                                                    "selected_answer": "A"}, headers={"X-CSRFToken": token})
            self.assertEqual(response.status_code, 403, path)
        self.assertEqual(self.client.get(f"/demo/1/quiz").status_code, 404)
        self.assertEqual(self.client.get("/api/participant/session-status").status_code, 200)
        self.finish(identifier, token)
        self.assertEqual(before, self.official_snapshot())
        with self.app.app_context():
            leaderboard_after = get_global_leaderboard()
            self.assertEqual(leaderboard_before["rows"], leaderboard_after["rows"])
            self.assertEqual(leaderboard_before["stations"], leaderboard_after["stations"])
            self.assertEqual(export_before, generate_results_csv(get_filtered_results()))
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 302)

    def test_csrf_size_limits_invalid_payload_and_disabled_mode(self):
        self.assertEqual(self.client.post("/demo/software/start").status_code, 400)
        identifier, token = self.start()
        self.assertEqual(self.answer(identifier, token, 1, {"1": "E"}).status_code, 400)
        response = self.client.post(f"/demo/{identifier}/answer", data="x" * 9000, content_type="application/json",
                                    headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 413)
        self.app.config["DEMO_ENABLED"] = False
        self.assertEqual(self.client.get("/demo/").status_code, 404)
        self.assertNotIn(b"Coba Demo", self.client.get("/").data)

    def test_rate_limits_and_unavailable_questions(self):
        self.app.config["DEMO_STARTS_PER_HOUR"] = 1
        self.start()
        response = self.client.post("/demo/software/start", data={"csrf_token": self.csrf()})
        self.assertEqual(response.status_code, 429)
        self.app.config["DEMO_STARTS_PER_HOUR"] = 12
        with patch.object(store, "load_pack", return_value={"questions": []}):
            response = self.client.post("/demo/software/start", data={"csrf_token": self.csrf()})
            self.assertEqual(response.status_code, 503)
        with patch.object(store, "load_pack", side_effect=ValueError("unavailable")):
            response = self.client.post("/demo/software/start", data={"csrf_token": self.csrf()})
            self.assertEqual(response.status_code, 503)

    def test_concurrent_finalization_produces_single_result(self):
        identifier, token = self.start()
        for member in (1, 2):
            self.client.post(f"/demo/{identifier}/advance", data={"csrf_token": token, "member": member, "revision": self.read(identifier)["revision"]})
        original = self.read(identifier)
        def submit(_):
            with self.app.app_context():
                return store.access_attempt(identifier, original["owner"], "submit",
                                            {"member": 3, "answers": {"9": "A"}, "revision": original["revision"]})["result"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(4)))
        self.assertTrue(all(result == results[0] for result in results))


if __name__ == "__main__":
    unittest.main(verbosity=2)
