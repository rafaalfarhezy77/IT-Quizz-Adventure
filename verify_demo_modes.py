"""Access policy and four-station practice acceptance tests on temporary stores."""
import re
import unittest
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
import verify_demo as baseline
from models import Admin, CompetitionSession, SessionStatus, WebsiteAccessAudit, db
from services import demo_service as store
from services.demo_packs import load_pack
from services.access_service import set_public_mode
from werkzeug.security import generate_password_hash


class DemoModesTest(unittest.TestCase):
    setUp = baseline.DemoTest.setUp
    tearDown = baseline.DemoTest.tearDown
    csrf = baseline.DemoTest.csrf
    read = baseline.DemoTest.read
    official_snapshot = baseline.DemoTest.official_snapshot

    def admin(self, active=True):
        with self.app.app_context():
            admin = Admin(username="policy-admin", password_hash=generate_password_hash("test-password"), is_active=active)
            db.session.add(admin)
            db.session.commit()
            identifier = admin.id
        with self.client.session_transaction() as s:
            s.update(admin_id=identifier, admin_station_id=0)
        return identifier

    def start(self, slug):
        page = self.client.get(f"/demo/{slug}/rules")
        self.assertEqual(page.status_code, 200)
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = self.client.post(f"/demo/{slug}/start", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        identifier = response.location.split("/")[2]
        if response.location.endswith("case-study"):
            self.client.post(response.location, data={"csrf_token": token})
        return identifier, token

    def payload(self, identifier, **extra):
        a = self.read(identifier)
        return {"revision": a["revision"], "member": a["member"], "stage": a["state"].get("stage"), **extra}

    def save(self, identifier, token, **extra):
        return self.client.post(f"/demo/{identifier}/answer", json=self.payload(identifier, **extra), headers={"X-CSRFToken": token})

    def post(self, identifier, token, action, answers=None, **extra):
        data = self.payload(identifier, csrf_token=token, **extra)
        data.update({f"question_{key}": value for key, value in (answers or {}).items()})
        return self.client.post(f"/demo/{identifier}/{action}", data=data)

    def test_access_policy_public_lock_admin_exception_audit_and_reopen(self):
        self.admin()
        token = self.csrf()
        self.assertEqual(self.client.post("/admin/access-settings", data={"csrf_token": token, "mode": "DEMO_ONLY"}).status_code, 302)
        self.assertEqual(self.client.get("/admin/access-settings").status_code, 200)
        public = self.app.test_client()
        self.assertEqual(public.get("/demo/").status_code, 200)
        self.assertNotIn(b"MASUK SEBAGAI PESERTA", public.get("/").data)
        for path in ("/participant/access", "/participant/quiz", "/participant/leaderboard", "/admin/questions", "/uploads/hardware/evidence.png", "/api/foundation-summary"):
            self.assertEqual(public.get(path).status_code, 403, path)
        self.assertEqual(public.get("/admin/login").status_code, 200)
        self.assertEqual(public.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/participant/access").status_code, 200)
        self.assertEqual(self.client.get("/admin/questions").status_code, 200)
        with public.session_transaction() as s:
            s.update(participant_authorized=True, demo_owner="retain-this-owner")
        self.assertEqual(public.post("/participant/access", data={"access_code": "QUEST2026"}).status_code, 403)
        with public.session_transaction() as s:
            self.assertNotIn("participant_authorized", s)
            self.assertEqual(s["demo_owner"], "retain-this-owner")
        self.assertEqual(self.client.post("/admin/access-settings", data={"csrf_token": token, "mode": "NORMAL"}).status_code, 302)
        self.assertEqual(public.get("/participant/access").status_code, 200)
        with self.app.app_context():
            self.assertEqual(db.session.query(WebsiteAccessAudit).count(), 2)

    def test_demo_only_overrides_environment_without_restart_and_persists(self):
        identifier = self.admin()
        self.app.config["DEMO_ENABLED"] = False
        self.assertEqual(self.client.get("/demo/").status_code, 404)
        with self.app.app_context():
            store.initialize()
            set_public_mode("DEMO_ONLY", identifier)
        self.assertEqual(self.app.test_client().get("/demo/").status_code, 200)
        from quiz_app import create_app
        class SecondWorker:
            pass
        for key, value in self.app.config.items():
            setattr(SecondWorker, key, value)
        other_app = create_app(SecondWorker)
        self.assertEqual(other_app.test_client().get("/participant/access").status_code, 403)
        with other_app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_active_competition_rejects_mode_change_and_inactive_admin_denied(self):
        self.admin()
        token = self.csrf()
        with self.app.app_context():
            competition = db.session.get(CompetitionSession, 1)
            competition.status = SessionStatus.RUNNING
            db.session.commit()
        self.assertEqual(self.client.post("/admin/access-settings", data={"csrf_token": token, "mode": "DEMO_ONLY"}).status_code, 409)
        with self.app.app_context():
            self.assertEqual(db.session.query(WebsiteAccessAudit).count(), 0)
            db.session.query(Admin).update({"is_active": False})
            db.session.commit()
        self.assertEqual(self.client.get("/api/admin/sessions/1/status").status_code, 401)
        self.assertEqual(self.client.get("/admin/access-settings").status_code, 302)

    def test_cyber_full_flow_keys_hidden_and_official_data_unchanged(self):
        before = self.official_snapshot()
        identifier, token = self.start("cyber")
        page = self.client.get(f"/demo/{identifier}/quiz")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"correct_answer", page.data)
        answers = {str(q["id"]): q["correct_answer"] for q in load_pack("cyber")["questions"]}
        self.assertEqual(self.save(identifier, token, answers=answers).status_code, 200)
        self.assertEqual(self.post(identifier, token, "submit", answers).status_code, 302)
        self.assertEqual(self.read(identifier)["result"]["raw_score"], 60)
        self.assertIn(b"Jawaban benar", self.client.get(f"/demo/{identifier}/result").data)
        self.assertEqual(before, self.official_snapshot())

    def test_networking_three_stages_auto_scoring_stamp_and_locked_answers(self):
        before = self.official_snapshot()
        identifier, token = self.start("networking")
        pack = load_pack("networking")
        for stage in (1, 2, 3):
            page = self.client.get(f"/demo/{identifier}/quiz")
            self.assertEqual(page.status_code, 200)
            self.assertNotIn(b"accepted", page.data)
            self.assertNotIn(b"correct_answer", page.data)
            for q in [q for q in pack["questions"] if q["stage"] == stage]:
                self.assertEqual(self.save(identifier, token, answers={str(q["id"]): q["correct_answer"]}).status_code, 200)
            if stage < 3:
                first = next(q for q in pack["questions"] if q["stage"] == stage)
                self.assertEqual(self.save(identifier, token, answers={str(first["id"]): "E" if stage == 1 else "Salah"}).status_code, 409)
                self.assertEqual(self.post(identifier, token, "advance").status_code, 200)
                self.assertEqual(self.post(identifier, token, "begin-stage").status_code, 302)
        self.assertEqual(self.post(identifier, token, "submit").status_code, 302)
        a = self.read(identifier)
        self.assertEqual(a["result"]["raw_score"], 100)
        self.assertTrue(a["result"]["has_stamp"])
        self.assertEqual(a["result"]["stage_scores"], {"1": 30.0, "2": 40.0, "3": 30.0})
        self.assertEqual(self.client.get(f"/demo/{identifier}/result").status_code, 200)
        self.assertEqual(before, self.official_snapshot())

    def test_networking_timeouts_transition_and_overall_deadline(self):
        identifier, token = self.start("networking")
        initial = self.read(identifier)
        with patch.object(store, "now", return_value=initial["state"]["stage_deadline"] + 1):
            a = self.read(identifier)
            self.assertEqual(a["state"]["awaiting_stage"], 2)
            self.assertEqual(self.client.get(f"/demo/{identifier}/quiz").status_code, 200)
            self.assertEqual(self.post(identifier, token, "begin-stage").status_code, 302)
        with patch.object(store, "now", return_value=initial["deadline"] + 1):
            self.assertEqual(self.read(identifier)["status"], "TIMED_OUT")
            self.assertEqual(self.read(identifier)["result"]["time_bonus"], 0)

    def test_hardware_server_scoring_draft_and_example_only_after_finish(self):
        before = self.official_snapshot()
        identifier, token = self.start("hardware")
        pack = load_pack("hardware")
        chosen = {cat: options[0]["id"] for cat, options in pack["catalogue"].items()}
        page = self.client.get(f"/demo/{identifier}/quiz")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"example", page.data)
        self.assertEqual(self.save(identifier, token, components=chosen, rationale="Sesuai budget", total_price=1, cpu_score=99999).status_code, 200)
        self.assertEqual(self.read(identifier)["state"]["components"], chosen)
        self.assertEqual(self.client.get(f"/demo/{identifier}/quiz").status_code, 200)
        data = {f"component_{cat}": value for cat, value in chosen.items()}
        self.assertEqual(self.post(identifier, token, "submit", rationale="Sesuai budget", **data).status_code, 302)
        a = self.read(identifier)
        self.assertEqual(a["result"]["total_price"], 830)
        self.assertEqual(a["result"]["raw_score"], 95)
        self.assertTrue(all(a["result"]["checks"].values()))
        result = self.client.get(f"/demo/{identifier}/result")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Contoh konfigurasi", result.data)
        self.assertEqual(before, self.official_snapshot())

    def test_hardware_incompatibility_budget_and_unknown_components(self):
        identifier, token = self.start("hardware")
        chosen = {cat: options[-1]["id"] for cat, options in load_pack("hardware")["catalogue"].items()}
        chosen["cpu"] = "cpu-2"
        self.assertEqual(self.save(identifier, token, components={"cpu": "not-a-component"}).status_code, 400)
        data = {f"component_{cat}": value for cat, value in chosen.items()}
        self.post(identifier, token, "submit", rationale="Uji kompatibilitas", **data)
        self.assertFalse(self.read(identifier)["result"]["checks"]["socket"])
        with self.app.app_context():
            pack = load_pack("hardware")
            pack["rules"]["max_budget"] = 100
            result = store.hardware_evaluation(pack, {"components": chosen}, 0)
            self.assertEqual(result["breakdown"]["budget"]["achieved"], 0)

    def test_revision_conflict_resume_and_guide_allowlist(self):
        identifier, token = self.start("cyber")
        old = self.payload(identifier, answers={"1": "A"})
        self.assertEqual(self.save(identifier, token, answers={"1": "B"}).status_code, 200)
        response = self.client.post(f"/demo/{identifier}/answer", json=old, headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.read(identifier)["answers"], {"1": "B"})
        self.assertIn(identifier.encode(), self.client.get("/demo/").data)
        for kind in ("html", "pdf"):
            response = self.client.get(f"/demo/guide/{kind}")
            self.assertEqual(response.status_code, 200)
            response.close()
        self.assertEqual(self.client.get("/demo/guide/demo_service.py").status_code, 404)

    def test_all_stations_browser_ownership_timeout_and_finalized_writes(self):
        other = self.app.test_client()
        for slug in ("software", "cyber", "networking", "hardware"):
            identifier, token = self.start(slug)
            self.assertEqual(other.get(f"/demo/{identifier}/quiz").status_code, 404)
            a = self.read(identifier)
            with patch.object(store, "now", return_value=a["deadline"] + 1):
                result = self.read(identifier)
                self.assertEqual(result["status"], "TIMED_OUT")
                self.assertEqual(result["result"]["time_bonus"], 0)
                self.assertEqual(self.client.get(f"/demo/{identifier}/result").status_code, 200)
                self.assertEqual(self.save(identifier, token, answers={}).status_code, 409)

    def test_legacy_software_snapshot_and_idempotent_schema_upgrade(self):
        from services.demo_questions import load_pack as legacy_pack
        legacy_path = Path(self.tmp.name) / "legacy-demo.db"
        self.app.config["DEMO_DATABASE_PATH"] = str(legacy_path)
        pack = legacy_pack()
        pack.update(duration=240, bonus_rate=1)
        with sqlite3.connect(legacy_path) as conn:
            conn.execute("""CREATE TABLE attempts(id TEXT PRIMARY KEY,owner TEXT,ip_hash TEXT,created REAL,
                         deadline REAL,expires REAL,pack TEXT,answers TEXT DEFAULT '{}',member INTEGER DEFAULT 1,
                         seen INTEGER DEFAULT 0,status TEXT DEFAULT 'RUNNING',result TEXT)""")
            timestamp = store.now()
            conn.execute("INSERT INTO attempts(id,owner,ip_hash,created,deadline,expires,pack) VALUES(?,?,?,?,?,?,?)",
                         ("demo_legacy", "legacy-owner", "hash", timestamp, timestamp+240, timestamp+86400, json.dumps(pack)))
        with self.app.app_context():
            store.initialize()
            store.initialize()
            store.access_attempt("demo_legacy", "legacy-owner", "seen")
            a = store.access_attempt("demo_legacy", "legacy-owner", "answer", {"member": 1, "answers": {"1": "A"}})
            self.assertEqual(a["answers"], {"1": "A"})
            self.assertEqual(a["pack"]["version"], "software-v1")

    def test_official_start_and_policy_use_same_transaction_lock(self):
        admin_id = self.admin()
        from services.session_service import start_session
        with self.app.app_context():
            competition = db.session.get(CompetitionSession, 1)
            competition.status = SessionStatus.WAITING
            db.session.commit()
            success, message = start_session(competition)
            self.assertTrue(success, message)
            with self.assertRaises(ValueError):
                set_public_mode("DEMO_ONLY", admin_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
