"""Isolated Hardware JSON regression tests; never use competition.db."""
import copy
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from models import (db, Admin, Station, StationMode, Group, Team, ChallengePackage,
                    PackageStatus, CompetitionSession, SessionStatus, Submission, HardwareSubmission, utcnow)
from routes.admin import admin_bp
from routes.api import api_bp
from routes.participant import participant_bp
from services.hardware_json_import import parse_hardware_json, execute_hardware_import
from services.package_service import set_package_status
from services.package_mapping_service import apply_same_for_all_mapping, make_package_snapshot


class HardwareImportTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="templates")
        self.app.config.update(TESTING=True, SECRET_KEY="hardware-test", SQLALCHEMY_DATABASE_URI="sqlite://")
        db.init_app(self.app)
        CSRFProtect(self.app)
        for bp in (admin_bp, api_bp, participant_bp):
            self.app.register_blueprint(bp)
        self.app.add_url_rule("/", "index", lambda: "index")
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_patch = patch("services.question_json_import.get_temp_upload_dir", return_value=Path(self.tmp.name))
        self.tmp_patch.start()
        self.station = Station(name="Hardware", mode=StationMode.BELUM_DIKETAHUI)
        self.other = Station(name="Software Engineering")
        self.admin = Admin(username="test", password_hash="test")
        self.groups = [Group(code=code) for code in "ABCD"]
        db.session.add_all([self.station, self.other, self.admin, *self.groups])
        db.session.flush()
        self.team = Team(team_code="A01", team_name="Dummy", school="School", group=self.groups[0])
        db.session.add(self.team)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess.update(admin_id=self.admin.id, admin_station_id=self.station.id)
        self.sample = json.loads(Path("bank_soal_hardware.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.tmp_patch.stop()
        self.tmp.cleanup()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def path(self, data):
        path = Path(self.tmp.name) / "fixture.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def package(self):
        return db.session.scalar(db.select(ChallengePackage))

    def csrf(self, response):
        return re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data).group(1).decode()

    def upload(self, data=None, mode="ADD"):
        page = self.client.get("/admin/packages/import")
        token = self.csrf(page)
        response = self.client.post("/admin/packages/import", data={"csrf_token": token, "mode": mode,
            "file": (io.BytesIO(json.dumps(data or self.sample).encode()), "hardware.json")}, content_type="multipart/form-data")
        with self.client.session_transaction() as sess:
            pending = dict(sess.get("hardware_import") or {})
        return response, token, pending

    def test_add_many_update_and_defaults(self):
        data = copy.deepcopy(self.sample)
        second = copy.deepcopy(data["packages"][0]); second["package_code"] = "Paket 02"
        data["packages"].append(second)
        self.assertTrue(execute_hardware_import(self.path(data), self.station.id, "ADD")[0])
        self.assertEqual(db.session.query(ChallengePackage).count(), 2)
        package = self.package()
        self.assertEqual(package.status, PackageStatus.DRAFT)
        self.assertEqual(package.rules_config["budget_max"], 1500)
        self.assertEqual(package.scoring_config["weight_cpu"], 15)
        package.status = PackageStatus.ACTIVE
        db.session.commit()
        data = copy.deepcopy(self.sample)
        item = data["packages"][0]
        item["package_code"] = "  pAKET 01  "
        item["title"] = "Updated"
        item["rules_config"] = {key: item["rules_config"][key] for key in ("max_budget", "currency", "min_cpu_score", "min_gpu_score", "min_ram_gb", "min_storage_gb")}
        item["rules_config"]["min_cpu_score"] = 0
        item["scoring_config"].update(weight_cpu_target=0, weight_gpu_target=35)
        self.assertTrue(execute_hardware_import(self.path(data), self.station.id, "UPDATE")[0])
        self.assertEqual(package.title, "Updated")
        self.assertEqual(package.status, PackageStatus.ACTIVE)
        self.assertEqual(package.package_code, "Paket 01")
        self.assertEqual(package.rules_config["min_cpu_score"], 0)
        self.assertEqual(package.rules_config["region"], "United States")
        self.assertFalse(package.rules_config["used_parts_allowed"])
        self.assertEqual(package.scoring_config["weight_cpu"], 0)

    def test_invalid_fields_and_no_partial_import(self):
        changes = [("title", ""), ("description", None), ("instructions", " "),
                   ("external_tool_url", "javascript:alert(1)"), ("duration_minutes", 0),
                   ("duration_minutes", 181), ("duration_minutes", 30.5), ("status", "ACTIVE"),
                   ("rules_config", []), ("scoring_config", None), ("package_code", "X"*31)]
        for key, value in changes:
            data = copy.deepcopy(self.sample)
            bad = copy.deepcopy(data["packages"][0]); bad.update(package_code="Paket 02")
            bad[key] = value; data["packages"].append(bad)
            with self.subTest(key=key, value=value):
                self.assertFalse(execute_hardware_import(self.path(data), self.station.id, "ADD")[0])
                self.assertEqual(db.session.query(ChallengePackage).count(), 0)
        for key, value in (("max_budget", -1), ("max_budget", "1000"), ("min_ram_gb", False),
                           ("used_parts_allowed", "false"), ("min_cpu_score", float("inf")), ("unknown", 1)):
            data = copy.deepcopy(self.sample); data["packages"][0]["rules_config"][key] = value
            self.assertFalse(parse_hardware_json(self.path(data), self.station.id)["is_valid"])
        data = copy.deepcopy(self.sample); data["packages"][0]["scoring_config"]["weight_gpu_target"] = 90
        self.assertFalse(parse_hardware_json(self.path(data), self.station.id)["is_valid"])

    def test_structure_duplicates_target_and_size(self):
        for data in ([], {"station": "Hardware", "packages": []}, {"station": "Other", "packages": self.sample["packages"]}):
            self.assertFalse(parse_hardware_json(self.path(data), self.station.id)["is_valid"])
        data = copy.deepcopy(self.sample)
        data["packages"].append(copy.deepcopy(data["packages"][0]))
        data["packages"][1]["package_code"] = " paket 01 "
        self.assertFalse(parse_hardware_json(self.path(data), self.station.id)["is_valid"])
        self.assertFalse(parse_hardware_json(self.path(self.sample), self.other.id)["is_valid"])
        self.assertFalse(parse_hardware_json(self.path(self.sample), self.station.id, "WRONG")["is_valid"])
        self.assertFalse(execute_hardware_import(self.path(self.sample), self.station.id, "UPDATE")[0])
        path = self.path(self.sample); path.write_text('{"station":"Hardware","station":"Hardware"}', encoding="utf-8")
        self.assertFalse(parse_hardware_json(path, self.station.id)["is_valid"])
        path.write_text("x" * (5 * 1024 * 1024 + 1), encoding="utf-8")
        self.assertFalse(parse_hardware_json(path, self.station.id)["is_valid"])

    def test_duplicate_existing_and_ambiguous(self):
        self.assertTrue(execute_hardware_import(self.path(self.sample), self.station.id, "ADD")[0])
        self.assertFalse(execute_hardware_import(self.path(self.sample), self.station.id, "ADD")[0])
        package = self.package()
        db.session.add(ChallengePackage(station=self.station, package_code="paket 01", title="Other",
                                       description="Other", instructions="Other"))
        db.session.commit()
        self.assertFalse(parse_hardware_json(self.path(self.sample), self.station.id, "UPDATE")["is_valid"])

    def test_rollback_late_failure_add_update(self):
        import services.hardware_json_import as importer
        data = copy.deepcopy(self.sample)
        other = copy.deepcopy(data["packages"][0]); other["package_code"] = "Paket 02"
        data["packages"].append(other)
        original = importer.create_package
        def fail_second(**kwargs):
            if kwargs["package_code"] == "Paket 02":
                raise RuntimeError("late failure")
            return original(**kwargs)
        with patch.object(importer, "create_package", side_effect=fail_second):
            self.assertFalse(execute_hardware_import(self.path(data), self.station.id, "ADD")[0])
        self.assertEqual(db.session.query(ChallengePackage).count(), 0)
        self.assertTrue(execute_hardware_import(self.path(data), self.station.id, "ADD")[0])
        old = self.package().title
        data["packages"][0]["title"] = "Changed"
        with patch.object(db.session, "commit", side_effect=RuntimeError("commit failure")):
            self.assertFalse(execute_hardware_import(self.path(data), self.station.id, "UPDATE")[0])
        self.assertEqual(self.package().title, old)

    def test_preview_confirm_cancel_and_security(self):
        malicious = copy.deepcopy(self.sample); malicious["packages"][0]["description"] = "<script>bad</script>"
        page, token, pending = self.upload(malicious)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"&lt;script&gt;", page.data)
        self.assertEqual(db.session.query(ChallengePackage).count(), 0)
        self.assertEqual(self.client.post("/admin/packages/import/confirm", data={"file_token": pending["token"]}).status_code, 400)
        response = self.client.post("/admin/packages/import/confirm", data={"csrf_token": token, "file_token": pending["token"], "mode": "UPDATE"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.package().status, PackageStatus.DRAFT)
        self.assertFalse((Path(self.tmp.name) / (pending["token"] + ".json")).exists())
        with self.client.get("/admin/packages/sample.json") as download:
            self.assertEqual(download.status_code, 200)
        page, token, pending = self.upload(mode="UPDATE")
        self.client.post("/admin/packages/import/cancel", data={"csrf_token": token, "file_token": pending["token"]})
        self.assertFalse((Path(self.tmp.name) / (pending["token"] + ".json")).exists())
        self.assertEqual(self.app.test_client().get("/admin/packages/import").status_code, 302)
        with self.client.session_transaction() as sess:
            sess["admin_station_id"] = self.other.id
        self.assertEqual(self.client.get("/admin/packages/import").status_code, 403)

    def test_locked_waiting_running_and_stale_preview(self):
        self.assertTrue(execute_hardware_import(self.path(self.sample), self.station.id, "ADD")[0])
        package = self.package()
        old_title = package.title
        changed = copy.deepcopy(self.sample)
        changed["packages"][0]["title"] = "Must not be saved"
        page, token, pending = self.upload(changed, mode="UPDATE")
        self.assertNotIn(b"IMPOR DIBLOKIR", page.data)
        package.status = PackageStatus.LOCKED; db.session.commit()
        self.client.post("/admin/packages/import/confirm", data={"csrf_token": token, "file_token": pending["token"]})
        self.assertEqual(package.status, PackageStatus.LOCKED)
        self.assertEqual(package.title, old_title)
        self.assertFalse(parse_hardware_json(self.path(self.sample), self.station.id, "UPDATE")["is_valid"])
        package.status = PackageStatus.ACTIVE
        competition = CompetitionSession(station=self.station, group=self.groups[0], package=package, duration_seconds=1800)
        db.session.add(competition); db.session.commit()
        for status in (SessionStatus.WAITING, SessionStatus.RUNNING):
            competition.status = SessionStatus.FINISHED
            db.session.commit()
            page, token, pending = self.upload(changed, mode="UPDATE")
            self.assertNotIn(b"IMPOR DIBLOKIR", page.data)
            competition.status = status; db.session.commit()
            self.assertFalse(parse_hardware_json(self.path(self.sample), self.station.id, "UPDATE")["is_valid"])
            self.client.post("/admin/packages/import/confirm", data={"csrf_token": token, "file_token": pending["token"]})
            self.assertEqual(package.title, old_title)

    def test_expiry_token_owner_and_missing_file(self):
        for change in ("expires_at", "admin_id", "station_id", "missing", "wrong_token"):
            page, token, pending = self.upload()
            with self.client.session_transaction() as sess:
                updated = dict(sess["hardware_import"])
                if change in ("expires_at", "admin_id", "station_id"):
                    updated[change] = 0
                    sess["hardware_import"] = updated
            if change == "missing":
                (Path(self.tmp.name) / (pending["token"] + ".json")).unlink()
            self.client.post("/admin/packages/import/confirm", data={"csrf_token": token,
                            "file_token": "wrong" if change == "wrong_token" else pending["token"]})
            self.assertEqual(db.session.query(ChallengePackage).count(), 0)

    def test_mapping_participant_and_snapshot(self):
        self.assertTrue(execute_hardware_import(self.path(self.sample), self.station.id, "ADD")[0])
        package = self.package()
        self.assertTrue(set_package_status(package.id, PackageStatus.ACTIVE)[0])
        self.assertTrue(apply_same_for_all_mapping(self.station.id, package.id)[0])
        snapshot = make_package_snapshot(package)
        historical = CompetitionSession(station=self.station, group=self.groups[0], package=package,
                                         duration_seconds=1800, status=SessionStatus.FINISHED)
        submission = Submission(session=historical, team=self.team, package=package, package_snapshot=snapshot)
        db.session.add(submission); db.session.commit()
        data = copy.deepcopy(self.sample); data["packages"][0]["title"] = "Revision"
        self.assertTrue(execute_hardware_import(self.path(data), self.station.id, "UPDATE")[0])
        self.assertEqual(submission.package_snapshot, snapshot)
        competition = CompetitionSession(station=self.station, group=self.groups[0], package=package,
                                          duration_seconds=1800, status=SessionStatus.RUNNING, started_at=utcnow())
        db.session.add(competition); db.session.commit()
        with self.client.session_transaction() as sess:
            sess.update(participant_authorized=True, participant_station_id=self.station.id,
                        participant_group_id=self.groups[0].id, participant_team_id=self.team.id,
                        participant_confirmed=True, participant_rules_accepted=True)
        page = self.client.get("/participant/quiz")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Revision", page.data)
        self.assertIn(b"1500", page.data)


if __name__ == "__main__":
    unittest.main()
