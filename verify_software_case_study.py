"""Isolated regression tests for set cases, atomic imports, and participant flow."""
import copy
import io
import json
import re
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.datastructures import FileStorage
from models import (db, Admin, Station, StationMode, Group, Team, QuestionSet,
                    QuestionSetStatus, Question, CompetitionSession, SessionStatus,
                    Submission, SubmissionStatus, utcnow)
from routes.admin import admin_bp
from routes.api import api_bp
from routes.participant import participant_bp
from services.question_json_import import parse_and_validate_question_json, execute_question_import, save_temp_json
from services.quiz_service import save_answer, partition_questions_for_members
from services.scoring_service import calculate_scores
from migrations.upgrade_schema import upgrade_database_schema


class SoftwareCaseStudyTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="templates")
        self.app.config.update(TESTING=True, SECRET_KEY="case-study-test",
                               SQLALCHEMY_DATABASE_URI="sqlite://", MEMBER_ROTATION_COUNT=3,
                               TIME_BONUS_PER_SECOND=1)
        db.init_app(self.app)
        CSRFProtect(self.app)
        for blueprint in (admin_bp, api_bp, participant_bp):
            self.app.register_blueprint(blueprint)
        self.app.add_url_rule("/", "index", lambda: "index")
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.tmp = tempfile.TemporaryDirectory()
        self.upload_patch = patch("services.question_json_import.get_temp_upload_dir", return_value=Path(self.tmp.name))
        self.upload_patch.start()
        self.station = Station(name="Software Engineering", mode=StationMode.MEMBER_ROTATION)
        self.group = Group(code="A")
        self.admin = Admin(username="test", password_hash="test")
        db.session.add_all([self.station, self.group, self.admin])
        db.session.flush()
        self.sets = {code: QuestionSet(station=self.station, code=code, name=f"Set {code}", status=QuestionSetStatus.READY) for code in "ABCD"}
        self.team = Team(team_code="A01", team_name="Team", school="School", group=self.group)
        db.session.add_all([*self.sets.values(), self.team])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(admin_id=self.admin.id, admin_station_id=0,
                           participant_authorized=True, participant_station_id=self.station.id,
                           participant_group_id=self.group.id, participant_team_id=self.team.id,
                           participant_confirmed=True, participant_rules_accepted=True)

    def tearDown(self):
        self.upload_patch.stop()
        self.tmp.cleanup()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def questions(self, code="A"):
        return [{"external_id": f"SE-{code}-{i}", "order_number": i, "member": (i-1)//3+1,
                 "text": f"Question {i}", "options": {key: f"Option {key}" for key in "ABCD"},
                 "correct_answer": "D", "weight": 10} for i in range(1, 10)]

    def payload(self, codes="A", legacy=False):
        return {"sets": {code: self.questions(code) if legacy else {
            "case_study": {"title": f"Case {code} <script>unsafe</script>", "description": "Scenario\nRead carefully."},
            "questions": self.questions(code)} for code in codes}}

    def upload(self, data):
        return save_temp_json(FileStorage(stream=io.BytesIO(json.dumps(data).encode()), filename="bank.json"))

    def import_data(self, data, mode="ADD"):
        token, _ = self.upload(data)
        return execute_question_import(token, self.station.id, mode)

    def csrf(self, page):
        return re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data).group(1).decode()

    def start_session(self, status=SessionStatus.RUNNING):
        competition = CompetitionSession(station=self.station, group=self.group, question_set=self.sets["A"],
                                          status=status, duration_seconds=600, started_at=utcnow() - timedelta(seconds=30))
        db.session.add(competition)
        db.session.commit()
        return competition

    def test_new_format_and_admin_preview(self):
        data = self.payload("ABCD")
        token, path = self.upload(data)
        validation = parse_and_validate_question_json(path, self.station.id)
        self.assertTrue(validation["is_valid"], validation)
        self.assertEqual(validation["total_questions"], 36)
        page = self.client.get("/admin/questions/import")
        response = self.client.post("/admin/questions/import", data={
            "csrf_token": self.csrf(page), "station_id": self.station.id, "mode": "ADD",
            "file": (io.BytesIO(json.dumps(data).encode()), "bank.json")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Scenario", response.data)
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertTrue(execute_question_import(token, self.station.id)[0])
        self.assertEqual(db.session.query(Question).count(), 36)
        self.assertEqual(self.sets["D"].case_study["description"], "Scenario\nRead carefully.")

    def test_admin_add_edit_and_list_case(self):
        page = self.client.get("/admin/questions")
        self.assertIn("Study case belum ada.".encode(), page.data)
        self.assertIn(b"+ TAMBAH STUDY CASE", page.data)
        endpoint = f"/admin/questions/set/{self.sets['A'].id}/case-study"
        page = self.client.get(endpoint)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.client.post(endpoint, data={"title": "Case", "description": "Text"}).status_code, 400)
        data = {"csrf_token": self.csrf(page), "title": "   ", "description": "Text"}
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 200)
        self.assertIsNone(self.sets["A"].case_study)
        data.update(title="  New <script>case</script>  ", description="  Scenario\nNext line  ")
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 302)
        self.assertEqual(self.sets["A"].case_study["description"], "Scenario\nNext line")
        page = self.client.get("/admin/questions")
        self.assertIn(b"New &lt;script&gt;case&lt;/script&gt;", page.data)
        self.assertIn(b"UBAH STUDY CASE", page.data)
        self.assertEqual(self.client.get(endpoint).status_code, 200)
        data.update(title="Edited")
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 302)
        self.assertEqual(self.sets["A"].case_study["title"], "Edited")
        competition = self.start_session()
        self.assertIn(b"Edited", self.client.get("/participant/quiz").data)

    def test_admin_case_locked_running_and_station_access(self):
        endpoint = f"/admin/questions/set/{self.sets['A'].id}/case-study"
        token = self.csrf(self.client.get(endpoint))
        data = {"csrf_token": token, "title": "Denied", "description": "Denied"}
        self.sets["A"].status = QuestionSetStatus.LOCKED
        db.session.commit()
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 302)
        self.assertIsNone(self.sets["A"].case_study)
        self.sets["A"].status = QuestionSetStatus.READY
        self.start_session()
        self.assertEqual(self.client.post(endpoint, data=data).status_code, 302)
        self.assertIsNone(self.sets["A"].case_study)
        self.assertIn(b"STUDY CASE TERKUNCI", self.client.get("/admin/questions").data)
        other = Station(name="Cyber Security")
        db.session.add(other)
        db.session.commit()
        with self.client.session_transaction() as session:
            session["admin_station_id"] = other.id
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.assertEqual(self.app.test_client().get(endpoint).status_code, 302)

    def test_legacy_and_metadata_preservation(self):
        self.assertTrue(self.import_data(self.payload(legacy=True))[0])
        self.assertIsNone(self.sets["A"].case_study)
        self.assertTrue(self.import_data(self.payload(), "UPDATE")[0])
        original = copy.deepcopy(self.sets["A"].case_study)
        self.assertTrue(self.import_data(self.payload(legacy=True), "UPDATE")[0])
        self.assertEqual(self.sets["A"].case_study, original)
        envelope = self.payload()
        del envelope["sets"]["A"]["case_study"]
        self.assertTrue(self.import_data(envelope, "UPDATE")[0])
        self.assertEqual(self.sets["A"].case_study, original)
        self.assertEqual(db.session.query(Question).count(), 9)

    def test_failed_validation_is_atomic(self):
        variants = []
        for case in (None, {}, {"title": "", "description": "D"}, {"title": 1, "description": "D"}):
            data = self.payload("AB")
            data["sets"]["B"]["case_study"] = case
            variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"].pop(); variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["member"] = 3; variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["options"]["D"] = ""; variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["correct_answer"] = "E"; variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["order_number"] = 10; variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["order_number"] = 2; variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["options"]["E"] = "extra"; variants.append(data)
        data = self.payload("AB"); data["sets"]["B"]["questions"][0]["weight"] = float("nan"); variants.append(data)
        for data in variants:
            with self.subTest(data=data):
                self.assertFalse(self.import_data(data)[0])
                self.assertEqual(db.session.query(Question).count(), 0)
                self.assertIsNone(self.sets["A"].case_study)
        data = self.payload(); data["sets"][" a "] = data["sets"]["A"]
        self.assertFalse(self.import_data(data)[0])

    def test_locked_after_preview_and_rollback(self):
        token, path = self.upload(self.payload("AB"))
        self.assertTrue(parse_and_validate_question_json(path, self.station.id)["is_valid"])
        self.sets["B"].status = QuestionSetStatus.LOCKED
        db.session.commit()
        self.assertFalse(execute_question_import(token, self.station.id)[0])
        self.assertEqual(db.session.query(Question).count(), 0)
        self.assertIsNone(self.sets["A"].case_study)
        self.sets["B"].status = QuestionSetStatus.READY
        db.session.commit()
        with patch.object(db.session, "commit", side_effect=RuntimeError("simulated failure")):
            self.assertFalse(self.import_data(self.payload("AB"))[0])
        self.assertEqual(db.session.query(Question).count(), 0)
        self.assertIsNone(self.sets["A"].case_study)

    def test_update_failure_preserves_questions_and_case(self):
        self.assertTrue(self.import_data(self.payload("AB"))[0])
        original = copy.deepcopy(self.sets["A"].case_study)
        data = self.payload("AB")
        data["sets"]["A"]["case_study"]["title"] = "Changed"
        data["sets"]["A"]["questions"][0]["text"] = "Changed question"
        with patch.object(db.session, "commit", side_effect=RuntimeError("simulated failure")):
            self.assertFalse(self.import_data(data, "UPDATE")[0])
        self.assertEqual(self.sets["A"].case_study, original)
        self.assertEqual(self.sets["A"].questions[0].text, "Question 1")
        self.sets["B"].status = QuestionSetStatus.LOCKED
        db.session.commit()
        self.assertFalse(self.import_data(data, "UPDATE")[0])
        self.assertEqual(self.sets["A"].case_study, original)

    def test_root_alias_and_mixed_formats(self):
        data = {"A": self.payload()["sets"]["A"], "B": self.questions("B")}
        self.assertTrue(self.import_data(data)[0])
        self.assertIsNotNone(self.sets["A"].case_study)
        self.assertIsNone(self.sets["B"].case_study)
        self.assertTrue(self.import_data({"paket": {"C": self.questions("C")}})[0])

    def test_participant_intro_reopen_timer_and_scoring(self):
        self.assertTrue(self.import_data(self.payload())[0])
        competition = self.start_session()
        original_start = competition.started_at
        page = self.client.get("/participant/quiz")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'id="case-study-title"', page.data)
        self.assertNotIn(b'class="question-text"', page.data)
        self.assertNotIn(b"correct_answer", page.data)
        self.assertIn(b"&lt;script&gt;", page.data)
        self.assertIn(b"session_timer.js", page.data)
        self.assertIn(b'data-remaining="5', page.data)
        invalid = self.client.post("/participant/quiz/case-study")
        self.assertEqual(invalid.status_code, 400)
        submission = db.session.scalar(db.select(Submission))
        self.assertFalse(submission.case_study_seen)
        response = self.client.post("/participant/quiz/case-study", data={"csrf_token": self.csrf(page)})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(submission.case_study_seen)
        page = self.client.get("/participant/quiz")
        self.assertEqual(page.data.count(b'class="question-text"'), 3)
        self.assertIn(b"BUKA STUDI KASUS", page.data)
        self.assertNotIn(b"correct_answer", page.data)
        reopen = self.client.get("/participant/quiz/case-study")
        self.assertIn(b"KEMBALI KE SOAL", reopen.data)
        self.assertEqual(competition.started_at, original_start)
        self.assertEqual(submission.current_member, 1)
        before = int(re.search(rb'data-remaining="(\d+)"', reopen.data).group(1))
        competition.started_at = original_start - timedelta(seconds=10)
        db.session.commit()
        reopened_later = self.client.get("/participant/quiz/case-study")
        after = int(re.search(rb'data-remaining="(\d+)"', reopened_later.data).group(1))
        self.assertGreaterEqual(before - after, 10)
        partition = partition_questions_for_members(self.sets["A"].questions, 3)
        self.assertEqual([len(partition[i]) for i in (1, 2, 3)], [3, 3, 3])
        for question in partition[1]:
            self.assertTrue(save_answer(submission, question.id, "D")[0])
        submission.current_member = 2
        db.session.commit()
        page = self.client.get("/participant/quiz")
        self.assertEqual(page.data.count(b'class="question-text"'), 3)
        self.assertNotIn(b'id="case-study-title"', page.data)
        self.assertEqual(calculate_scores(submission).raw_score, 30)
        competition.started_at = utcnow() - timedelta(seconds=700)
        db.session.commit()
        self.assertEqual(self.client.get("/participant/quiz/case-study").status_code, 302)
        self.assertEqual(submission.status, SubmissionStatus.TIMED_OUT)

    def test_waiting_legacy_and_non_software(self):
        self.assertTrue(self.import_data(self.payload(legacy=True))[0])
        competition = self.start_session(SessionStatus.WAITING)
        response = self.client.get("/participant/quiz")
        self.assertIn("/waiting", response.location)
        self.assertEqual(db.session.query(Submission).count(), 0)
        competition.status = SessionStatus.RUNNING
        db.session.commit()
        self.assertNotIn(b'id="case-study-title"', self.client.get("/participant/quiz").data)
        self.station.name = "Cyber Security"
        self.sets["A"].case_study = {"title": "Not SE", "description": "Not SE"}
        db.session.commit()
        self.assertNotIn(b"BUKA STUDI KASUS", self.client.get("/participant/quiz").data)

    def test_migration_is_idempotent_and_sample(self):
        competition = self.start_session()
        existing = Submission(session=competition, team=self.team, current_member=2)
        db.session.add(existing)
        db.session.commit()
        with db.engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE question_sets DROP COLUMN case_study")
            connection.exec_driver_sql("ALTER TABLE submissions DROP COLUMN case_study_seen")
        upgrade_database_schema(self.app)
        upgrade_database_schema(self.app)
        db.session.expire_all()
        self.assertIsNone(self.sets["A"].case_study)
        self.assertEqual(db.session.query(Team).count(), 1)
        self.assertFalse(existing.case_study_seen)
        self.assertEqual(existing.current_member, 2)
        sample = parse_and_validate_question_json(Path("bank_soal.json"), self.station.id)
        self.assertTrue(sample["is_valid"], sample["global_errors"])
        self.assertEqual(sample["total_questions"], 36)


if __name__ == "__main__":
    unittest.main()
