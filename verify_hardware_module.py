import io
import json
import re
import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash

from config import Config
from quiz_app import create_app
from models import (
    Admin,
    Answer,
    ChallengePackage,
    ChallengeType,
    CompetitionSession,
    Group,
    GroupPackageMapping,
    HardwareSubmission,
    HardwareSubmissionAudit,
    HardwareVerificationStatus,
    MappingStrategy,
    PackageStatus,
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
from services.package_service import (
    create_package,
    duplicate_package,
    update_package,
    archive_package,
    delete_package,
    set_package_status,
    validate_scoring_weights,
)
from services.package_mapping_service import (
    save_package_mapping,
    get_assigned_package_for_group,
    validate_session_mapping_ready,
    make_package_snapshot,
)
from services.hardware_scoring_service import (
    calculate_hardware_provisional_score,
    evaluate_hardware_build,
)
from services.hardware_service import (
    save_hardware_draft,
    submit_hardware_build,
    review_hardware_submission,
)
from services.session_service import create_session, start_session, get_server_now
from services.leaderboard_service import get_session_leaderboard, calculate_rankings


# 1x1 valid PNG for testing valid image uploads
MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    PARTICIPANT_ACCESS_CODE = "QUEST2026"
    SECRET_KEY = "test-key-hw-module"
    TIME_BONUS_PER_SECOND = 1.0


class HardwareModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Seed Admin
            admin = Admin(username="admin_hw", password_hash=generate_password_hash("Secret123!"), is_active=True)
            db.session.add(admin)

            # Seed Stations
            st_hw = Station(name="Hardware", mode=StationMode.NORMAL, is_active=True)
            st_se = Station(name="Software Engineering", mode=StationMode.MEMBER_ROTATION, is_active=True)
            db.session.add_all([st_hw, st_se])
            db.session.flush()

            # Seed Groups A, B, C, D
            grp_a = Group(code="A")
            grp_b = Group(code="B")
            grp_c = Group(code="C")
            grp_d = Group(code="D")
            db.session.add_all([grp_a, grp_b, grp_c, grp_d])
            db.session.flush()

            # Seed Teams
            t_a1 = Team(team_code="A-01", team_name="Garuda Build", school="SMK 1", group_id=grp_a.id, is_active=True)
            t_b1 = Team(team_code="B-01", team_name="Nexus Rig", school="SMK 2", group_id=grp_b.id, is_active=True)
            t_c1 = Team(team_code="C-01", team_name="Silicon Squad", school="SMA 3", group_id=grp_c.id, is_active=True)
            t_d1 = Team(team_code="D-01", team_name="Byte Forge", school="SMA 4", group_id=grp_d.id, is_active=True)
            db.session.add_all([t_a1, t_b1, t_c1, t_d1])

            # Seed QuestionSet for Software Engineering
            qs_se = QuestionSet(station_id=st_se.id, code="A", name="Set A SoftEng", status=QuestionSetStatus.READY)
            db.session.add(qs_se)
            db.session.flush()

            q_se1 = Question(
                question_set_id=qs_se.id,
                text="Prinsip Single Responsibility adalah bagian dari?",
                option_a="SOLID",
                option_b="ACID",
                option_c="REST",
                option_d="DRY",
                correct_answer="A",
                weight=50.0,
                order_number=1,
                is_active=True,
            )
            q_se2 = Question(
                question_set_id=qs_se.id,
                text="Struktur data FIFO adalah?",
                option_a="Stack",
                option_b="Queue",
                option_c="Tree",
                option_d="Graph",
                correct_answer="B",
                weight=50.0,
                order_number=2,
                is_active=True,
            )
            db.session.add_all([q_se1, q_se2])

            db.session.commit()

            self.st_hw_id = st_hw.id
            self.st_se_id = st_se.id
            self.grp_a_id = grp_a.id
            self.grp_b_id = grp_b.id
            self.grp_c_id = grp_c.id
            self.grp_d_id = grp_d.id
            self.t_a1_id = t_a1.id
            self.t_b1_id = t_b1.id
            self.qs_se_id = qs_se.id

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
            "username": "admin_hw",
            "password": "Secret123!",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

    def setup_participant(self, client, station_id=None, group_id=None, team_id=None):
        st_id = station_id or self.st_hw_id
        g_id = group_id or self.grp_a_id
        t_id = team_id or self.t_a1_id

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

    def create_sample_hw_package(self, code="Paket 01", title="Paket 01 AI Lab", status=PackageStatus.ACTIVE):
        with self.app.app_context():
            pkg = create_package(
                station_id=self.st_hw_id,
                package_code=code,
                title=title,
                description="Studi kasus pengadaan PC AI Lab dengan batasan budget dan target performa.",
                instructions="1. Buka BuildCores. 2. Pilih komponen. 3. Masukkan data ke Mythic.",
                challenge_type=ChallengeType.HARDWARE_BUILD_CHALLENGE.value,
                external_tool_url="https://www.buildcores.com/builds",
                rules_config={
                    "budget_max": 25000000,
                    "currency": "IDR",
                    "region": "ID",
                    "min_cpu_score": 18000,
                    "min_gpu_score": 14000,
                    "min_ram_gb": 32,
                    "min_storage_gb": 1000,
                    "min_psu_watt": 650,
                    "required_components": ["GPU Dedicated", "SSD NVMe M.2"],
                    "forbidden_components": ["HDD Boot"],
                    "allow_used_parts": False,
                    "allow_custom_price": False,
                    "allow_discounts": False,
                    "notes": "Testing package",
                },
                scoring_config={
                    "weight_compatibility": 20.0,
                    "weight_budget": 15.0,
                    "weight_cpu": 15.0,
                    "weight_gpu": 20.0,
                    "weight_completeness": 10.0,
                    "weight_efficiency": 15.0,
                    "weight_time_bonus": 5.0,
                    "violation_penalty": 10.0,
                },
                duration_minutes=30,
                status=status,
            )
            return pkg.id

    # =========================================================================
    # TEST 1: Admin can create Hardware Package
    # =========================================================================
    def test_01_admin_create_hardware_package(self):
        self.login_admin(self.client)
        resp = self.client.get(f"/admin/packages/create?station_id={self.st_hw_id}")
        self.assertEqual(resp.status_code, 200)
        token = self.extract_csrf_token(resp.data.decode("utf-8"))

        post_data = {
            "csrf_token": token,
            "station_id": self.st_hw_id,
            "package_code": "Paket 01",
            "title": "Paket 01 Workstation Deep Learning",
            "description": "Deskripsi studi kasus perakitan workstation.",
            "instructions": "Petunjuk pengerjaan di BuildCores.",
            "external_tool_url": "https://www.buildcores.com/builds",
            "duration_minutes": 30,
            "status": "DRAFT",
            "max_budget": 25000000,
            "budget_max": 25000000,
            "currency": "IDR",
            "region": "ID",
            "min_cpu_score": 18000,
            "min_gpu_score": 14000,
            "min_ram_gb": 32,
            "min_storage_gb": 1000,
            "min_psu_watt": 650,
            "required_components": "GPU Dedicated\nSSD NVMe",
            "forbidden_components": "Integrated GPU Only",
            "allow_used_parts": "0",
            "allow_custom_price": "0",
            "allow_discounts": "0",
            "constraints_notes": "Catatan penting pengujian",
            "weight_compatibility": 20.0,
            "weight_budget": 15.0,
            "weight_cpu": 15.0,
            "weight_gpu": 20.0,
            "weight_completeness": 10.0,
            "weight_efficiency": 15.0,
            "weight_time_bonus": 5.0,
            "violation_penalty": 10.0,
        }
        res = self.client.post("/admin/packages/create", data=post_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Paket 01", res.data.decode("utf-8"))

        with self.app.app_context():
            pkg = db.session.scalar(db.select(ChallengePackage).where(ChallengePackage.package_code == "Paket 01"))
            self.assertIsNotNone(pkg)
            self.assertEqual(pkg.rules_config["budget_max"], 25000000)
            self.assertEqual(pkg.scoring_config["weight_compatibility"], 20.0)

    # =========================================================================
    # TEST 2: Admin can duplicate package
    # =========================================================================
    def test_02_admin_duplicate_package(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        self.login_admin(self.client)

        resp = self.client.get(f"/admin/packages/{pkg_id}/preview")
        token = self.extract_csrf_token(resp.data.decode("utf-8"))

        res = self.client.post(f"/admin/packages/{pkg_id}/duplicate", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            duplicated = db.session.scalar(
                db.select(ChallengePackage).where(ChallengePackage.id != pkg_id)
            )
            self.assertIsNotNone(duplicated)
            self.assertIn("Salinan", duplicated.title)
            self.assertEqual(duplicated.status, PackageStatus.DRAFT)
            self.assertEqual(duplicated.rules_config["budget_max"], 25000000)

    # =========================================================================
    # TEST 3: Admin cannot activate package with invalid weights (sum != 100)
    # =========================================================================
    def test_03_cannot_activate_package_with_invalid_weights(self):
        with self.app.app_context():
            invalid_config = {
                "weight_compatibility": 20.0,
                "weight_budget": 10.0,  # Total = 95 != 100
                "weight_cpu": 15.0,
                "weight_gpu": 20.0,
                "weight_completeness": 10.0,
                "weight_efficiency": 15.0,
                "weight_time_bonus": 5.0,
            }
            is_valid, err = validate_scoring_weights(invalid_config)
            self.assertFalse(is_valid)
            self.assertIn("100%", err)

            # Trying to set status ACTIVE directly via service should fail
            pkg = create_package(
                station_id=self.st_hw_id,
                package_code="Paket Invalid",
                title="Paket Invalid Weights",
                description="Desc",
                instructions="Instr",
                challenge_type=ChallengeType.HARDWARE_BUILD_CHALLENGE.value,
                scoring_config=invalid_config,
                status=PackageStatus.DRAFT,
            )
            ok, err_msg = set_package_status(pkg.id, PackageStatus.ACTIVE)
            self.assertFalse(ok)
            self.assertIn("Gagal mengaktifkan paket", err_msg)

    # =========================================================================
    # TEST 4: SAME_FOR_ALL assigns same package to all groups
    # =========================================================================
    def test_04_same_for_all_mapping(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            mappings = save_package_mapping(
                station_id=self.st_hw_id,
                strategy=MappingStrategy.SAME_FOR_ALL.value,
                same_package_id=pkg_id,
            )
            self.assertEqual(len(mappings), 4)
            for m in mappings:
                self.assertEqual(m.package_id, pkg_id)

            # Verify retrieval for every group
            for g_id in [self.grp_a_id, self.grp_b_id, self.grp_c_id, self.grp_d_id]:
                assigned = get_assigned_package_for_group(self.st_hw_id, g_id)
                self.assertIsNotNone(assigned)
                self.assertEqual(assigned.id, pkg_id)

    # =========================================================================
    # TEST 5: BY_GROUP assigns packages according to mapping
    # =========================================================================
    def test_05_by_group_mapping(self):
        p1_id = self.create_sample_hw_package(code="Paket 01", title="Paket 1", status=PackageStatus.ACTIVE)
        p2_id = self.create_sample_hw_package(code="Paket 02", title="Paket 2", status=PackageStatus.ACTIVE)
        p3_id = self.create_sample_hw_package(code="Paket 03", title="Paket 3", status=PackageStatus.ACTIVE)
        p4_id = self.create_sample_hw_package(code="Paket 04", title="Paket 4", status=PackageStatus.ACTIVE)

        with self.app.app_context():
            group_mapping = {
                self.grp_a_id: p1_id,
                self.grp_b_id: p2_id,
                self.grp_c_id: p3_id,
                self.grp_d_id: p4_id,
            }
            mappings = save_package_mapping(
                station_id=self.st_hw_id,
                strategy=MappingStrategy.BY_GROUP.value,
                group_package_map=group_mapping,
            )
            self.assertEqual(len(mappings), 4)

            # Group A receives P1, Group B receives P2
            self.assertEqual(get_assigned_package_for_group(self.st_hw_id, self.grp_a_id).id, p1_id)
            self.assertEqual(get_assigned_package_for_group(self.st_hw_id, self.grp_b_id).id, p2_id)
            self.assertEqual(get_assigned_package_for_group(self.st_hw_id, self.grp_c_id).id, p3_id)
            self.assertEqual(get_assigned_package_for_group(self.st_hw_id, self.grp_d_id).id, p4_id)

    # =========================================================================
    # TEST 6: Participant cannot access other group's package
    # =========================================================================
    def test_06_participant_isolation_per_group(self):
        p1_id = self.create_sample_hw_package(code="Paket 01", title="Paket Tim A", status=PackageStatus.ACTIVE)
        p2_id = self.create_sample_hw_package(code="Paket 02", title="Paket Tim B", status=PackageStatus.ACTIVE)

        with self.app.app_context():
            save_package_mapping(
                station_id=self.st_hw_id,
                strategy=MappingStrategy.BY_GROUP.value,
                group_package_map={
                    self.grp_a_id: p1_id,
                    self.grp_b_id: p2_id,
                },
            )

        # Participant from Group A logs in
        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)

        # Start session for Group A
        with self.app.app_context():
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=p1_id, duration_minutes=30)
            start_session(sess)

        resp = self.client.get("/participant/quiz")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Paket Tim A", html)
        self.assertNotIn("Paket Tim B", html)

    # =========================================================================
    # TEST 7: Session cannot start if group mapping is incomplete
    # =========================================================================
    def test_07_session_cannot_start_without_mapping(self):
        self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)

        with self.app.app_context():
            # No mapping exists yet for Group B
            is_ready, err, pkg = validate_session_mapping_ready(self.st_hw_id, self.grp_b_id)
            self.assertFalse(is_ready)
            self.assertIn("belum memiliki paket", err.lower())

            # Trying to start a session for unmapped group should fail
            sess = create_session(self.st_hw_id, self.grp_b_id, duration_minutes=30)
            ok, start_err = start_session(sess)
            self.assertFalse(ok)
            self.assertIn("belum memiliki paket", start_err.lower())

    # =========================================================================
    # TEST 8: Package is locked after session starts
    # =========================================================================
    def test_08_package_locked_after_session_start(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)

            pkg = db.session.get(ChallengePackage, pkg_id)
            self.assertEqual(pkg.status, PackageStatus.LOCKED)

    # =========================================================================
    # TEST 9: Refresh page does not reset server timer
    # =========================================================================
    def test_09_server_authoritative_timer(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=20)
            start_session(sess)
            sess_id = sess.id

        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)

        # First request
        r1 = self.client.get("/participant/quiz")
        self.assertEqual(r1.status_code, 200)

        # Fast forward session started_at in DB by 5 minutes
        with self.app.app_context():
            s = db.session.get(CompetitionSession, sess_id)
            s.started_at = s.started_at - timedelta(minutes=5)
            db.session.commit()

        # Second request (refresh page)
        r2 = self.client.get("/participant/quiz")
        self.assertEqual(r2.status_code, 200)

        # Check remaining time via API or verify remaining seconds is ~15 minutes (900s)
        api_res = self.client.get("/api/participant/session-status")
        self.assertEqual(api_res.status_code, 200)
        poll_data = json.loads(api_res.data.decode("utf-8"))
        remaining = poll_data.get("remaining_seconds", 0)
        self.assertGreater(remaining, 800)
        self.assertLessEqual(remaining, 905)

    # =========================================================================
    # TEST 10: Participant can save draft
    # =========================================================================
    def test_10_save_draft(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)

        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        draft_data = {
            "csrf_token": token,
            "buildcores_url": "https://www.buildcores.com/builds/draft123",
            "total_price": "22000000",
            "cpu_name": "Intel Core i7-14700K",
            "cpu_score": "21000",
            "gpu_name": "RTX 4070 Ti",
            "gpu_score": "16500",
            "ram_capacity_gb": "32",
            "storage_capacity_gb": "2000",
            "psu_name": "Corsair 750W",
            "components_summary": "Draft summary",
            "build_rationale": "Draft rationale",
        }
        res = self.client.post(
            "/participant/hardware/draft",
            json=draft_data,
            headers={"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(res.status_code, 200)
        resp_json = json.loads(res.data.decode("utf-8"))
        self.assertTrue(resp_json.get("success"))

        with self.app.app_context():
            sub = db.session.scalar(
                db.select(HardwareSubmission).join(Submission).where(Submission.team_id == self.t_a1_id)
            )
            self.assertIsNotNone(sub)
            self.assertEqual(sub.verification_status, "DRAFT")
            self.assertEqual(sub.cpu_name, "Intel Core i7-14700K")

    # =========================================================================
    # TEST 11: Participant can submit valid hardware configuration
    # =========================================================================
    def test_11_submit_valid_hardware_configuration(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)

        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)

        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        post_data = {
            "csrf_token": token,
            "buildcores_url": "https://www.buildcores.com/builds/valid-rig-99",
            "total_price": 24000000,
            "cpu_name": "AMD Ryzen 9 7900X",
            "cpu_score": 22000,
            "gpu_name": "NVIDIA RTX 4070",
            "gpu_score": 15000,
            "ram_capacity_gb": 32,
            "storage_capacity_gb": 1000,
            "psu_name": "Seasonic 750W",
            "components_summary": "Ryzen 9, RTX 4070, 32GB RAM, 1TB NVMe, Seasonic 750W",
            "build_rationale": "Sangat optimal untuk machine learning entry-level dengan alokasi budget efisien.",
            "screenshot": (io.BytesIO(MINIMAL_PNG_BYTES), "build_screenshot.png"),
            "confirmation_checked": "y",
        }

        res = self.client.post("/participant/hardware/submit", data=post_data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            sub = db.session.scalar(
                db.select(HardwareSubmission).join(Submission).where(Submission.team_id == self.t_a1_id)
            )
            self.assertIsNotNone(sub)
            self.assertEqual(sub.verification_status, "SUBMITTED")
            self.assertIsNotNone(sub.screenshot_filename)
            self.assertGreater(sub.provisional_score, 0)

    # =========================================================================
    # TEST 12: Submission cannot be edited once SUBMITTED
    # =========================================================================
    def test_12_submission_locked_after_submit(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)

        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)

        # Submit first
        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))
        post_data = {
            "csrf_token": token,
            "buildcores_url": "https://www.buildcores.com/builds/first-submit",
            "total_price": 24000000,
            "cpu_name": "AMD Ryzen 7",
            "cpu_score": 19000,
            "gpu_name": "RTX 4070",
            "gpu_score": 14500,
            "ram_capacity_gb": 32,
            "storage_capacity_gb": 1000,
            "psu_name": "750W",
            "components_summary": "Build summary",
            "build_rationale": "Rationale",
            "screenshot": (io.BytesIO(MINIMAL_PNG_BYTES), "screen.png"),
            "confirmation_checked": "y",
        }
        self.client.post("/participant/hardware/submit", data=post_data, content_type="multipart/form-data", follow_redirects=True)

        # Trying to submit again should redirect to result
        res2 = self.client.get("/participant/quiz", follow_redirects=True)

        # Draft attempt should return error
        draft_attempt = self.client.post(
            "/participant/hardware/draft",
            json={"total_price": "1000"},
            headers={"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(draft_attempt.status_code, 400)
        self.assertIn("tidak dapat diubah", draft_attempt.data.decode("utf-8"))

    # =========================================================================
    # TEST 13: Non-image and oversized uploads are rejected
    # =========================================================================
    def test_13_upload_security_validation(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)

        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)
        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # 1. Non-image file (plain text pretending to be png)
        fake_image = io.BytesIO(b"MALICIOUS_SCRIPT_OR_EXE_FILE_DATA_NOT_AN_IMAGE")
        bad_post = {
            "csrf_token": token,
            "buildcores_url": "https://www.buildcores.com/builds/fake",
            "total_price": 20000000,
            "cpu_name": "CPU",
            "cpu_score": 18000,
            "gpu_name": "GPU",
            "gpu_score": 14000,
            "ram_capacity_gb": 32,
            "storage_capacity_gb": 1000,
            "psu_name": "PSU",
            "components_summary": "Summary",
            "build_rationale": "Rationale",
            "screenshot": (fake_image, "fake.png"),
            "confirmation_checked": "y",
        }
        r1 = self.client.post("/participant/hardware/submit", data=bad_post, content_type="multipart/form-data", follow_redirects=True)
        self.assertTrue("gambar" in r1.data.decode("utf-8").lower() or "format" in r1.data.decode("utf-8").lower())

        # 2. Oversized file (> 5MB)
        huge_file = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"A" * (6 * 1024 * 1024))
        bad_post["screenshot"] = (huge_file, "huge.png")
        r2 = self.client.post("/participant/hardware/submit", data=bad_post, content_type="multipart/form-data", follow_redirects=True)
        self.assertTrue("besar" in r2.data.decode("utf-8").lower() or "maksimal" in r2.data.decode("utf-8").lower())

    # =========================================================================
    # TEST 14: Server calculates provisional score; final score only enters
    #          leaderboard after VERIFIED/SCORED
    # =========================================================================
    def test_14_provisional_vs_final_score_and_leaderboard(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)
            sess_id = sess.id

        self.setup_participant(self.client, station_id=self.st_hw_id, group_id=self.grp_a_id, team_id=self.t_a1_id)
        page = self.client.get("/participant/quiz")
        token = self.extract_csrf_token(page.data.decode("utf-8"))

        # Participant submits
        post_data = {
            "csrf_token": token,
            "buildcores_url": "https://www.buildcores.com/builds/leaderboard-test",
            "total_price": 24000000,
            "cpu_name": "AMD Ryzen 9",
            "cpu_score": 19000,
            "gpu_name": "RTX 4070",
            "gpu_score": 15000,
            "ram_capacity_gb": 32,
            "storage_capacity_gb": 1000,
            "psu_name": "750W",
            "components_summary": "Full components",
            "build_rationale": "Optimal setup",
            "screenshot": (io.BytesIO(MINIMAL_PNG_BYTES), "screenshot.png"),
            "confirmation_checked": "y",
        }
        self.client.post("/participant/hardware/submit", data=post_data, content_type="multipart/form-data", follow_redirects=True)

        # Check leaderboard before verification -> should NOT have final score
        with self.app.app_context():
            sub = db.session.scalar(
                db.select(HardwareSubmission).join(Submission).where(Submission.team_id == self.t_a1_id)
            )
            self.assertIsNotNone(sub)
            self.assertEqual(sub.verification_status, "SUBMITTED")
            self.assertGreater(sub.provisional_score, 0)

            # Check official Score table -> must not exist yet
            score_row = db.session.scalar(
                db.select(Score).join(Submission).where(Submission.team_id == self.t_a1_id)
            )
            self.assertIsNone(score_row)

            # Leaderboard query
            lb = get_session_leaderboard(sess_id)
            self.assertEqual(len(lb["ranked_rows"]), 0)  # Provisional not in ranked rows yet
            self.assertEqual(len(lb["uncompleted_rows"]), 1)

        # Now Admin reviews and verifies the submission
        self.login_admin(self.client)
        review_page = self.client.get(f"/admin/hardware/submissions/{sub.id}/review")
        self.assertEqual(review_page.status_code, 200)
        token_review = self.extract_csrf_token(review_page.data.decode("utf-8"))

        review_post = {
            "csrf_token": token_review,
            "action": "VERIFY",
            "is_compatible": "1",
            "corrected_price": 24000000,
            "corrected_cpu_score": 19000,
            "corrected_gpu_score": 15000,
            "reviewer_notes": "Spesifikasi dan screenshot valid sesuai BuildCores.",
            "reason": "Verifikasi panitia pos hardware selesai.",
        }
        rev_res = self.client.post(f"/admin/hardware/submissions/{sub.id}/review", data=review_post, follow_redirects=True)
        self.assertEqual(rev_res.status_code, 200)

        # Check that score is now in official leaderboard
        with self.app.app_context():
            sub_after = db.session.get(HardwareSubmission, sub.id)
            self.assertEqual(sub_after.verification_status, "VERIFIED")
            self.assertGreater(sub_after.final_score, 0)

            score_row_after = db.session.scalar(
                db.select(Score).join(Submission).where(Submission.team_id == self.t_a1_id)
            )
            self.assertIsNotNone(score_row_after)
            lb_after = get_session_leaderboard(sess_id)
            self.assertEqual(len(lb_after["ranked_rows"]), 1)
            self.assertEqual(lb_after["ranked_rows"][0]["final_score"], sub_after.final_score)
            self.assertGreater(lb_after["ranked_rows"][0]["final_score"], 80.0)

    # =========================================================================
    # TEST 15: Committee value modifications are logged in audit trail
    # =========================================================================
    def test_15_audit_logging_on_committee_changes(self):
        pkg_id = self.create_sample_hw_package(code="Paket 01", status=PackageStatus.ACTIVE)
        with self.app.app_context():
            save_package_mapping(self.st_hw_id, MappingStrategy.SAME_FOR_ALL.value, same_package_id=pkg_id)
            sess = create_session(self.st_hw_id, self.grp_a_id, package_id=pkg_id, duration_minutes=30)
            start_session(sess)

            # Create submitted hardware submission with underlying Submission
            sub_main = Submission(
                session_id=sess.id,
                team_id=self.t_a1_id,
                package_id=pkg_id,
                submission_type="hardware_build_challenge",
                status=SubmissionStatus.SUBMITTED,
                started_at=get_server_now(),
            )
            db.session.add(sub_main)
            db.session.flush()

            sub = HardwareSubmission(
                submission_id=sub_main.id,
                verification_status=HardwareVerificationStatus.SUBMITTED.value,
                provisional_score=75.0,
            )
            db.session.add(sub)
            db.session.commit()
            sub_id = sub.id

            admin = db.session.scalar(db.select(Admin).where(Admin.username == "admin_hw"))
            admin_id = admin.id

            # Review submission
            review_hardware_submission(
                submission_id=sub_id,
                reviewer_id=admin_id,
                verification_status=HardwareVerificationStatus.VERIFIED.value,
                compatibility_passed=True,
                budget_passed=True,
                cpu_target_passed=True,
                gpu_target_passed=True,
                completeness_passed=True,
                manual_score_override=92.0,
                reviewer_notes="Komponen sangat serasi.",
                audit_reason="Koreksi bonus performa.",
            )

            # Verify audit trail record
            audits = db.session.scalars(
                db.select(HardwareSubmissionAudit).where(HardwareSubmissionAudit.hardware_submission_id == sub_id)
            ).all()
            self.assertEqual(len(audits), 1)
            audit = audits[0]
            self.assertEqual(audit.action, "VERIFIED")
            self.assertEqual(audit.new_score, 92.0)
            self.assertEqual(audit.reason, "Koreksi bonus performa.")
            self.assertEqual(audit.changed_by, admin_id)

    # =========================================================================
    # TEST 16: Software Engineering quiz station continues to function normally
    # =========================================================================
    def test_16_software_engineering_quiz_station_regression(self):
        with self.app.app_context():
            sess = create_session(self.st_se_id, self.grp_a_id, self.qs_se_id, duration_minutes=15)
            start_session(sess)
            sess_id = sess.id

        self.setup_participant(self.client, station_id=self.st_se_id, group_id=self.grp_a_id, team_id=self.t_a1_id)

        # Participant opens quiz
        resp = self.client.get("/participant/quiz")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Prinsip Single Responsibility", html)
        self.assertIn("ROTASI ANGGOTA", html)

        token = self.extract_csrf_token(html)

        # Participant answers both questions via quiz_service and submits
        with self.app.app_context():
            from services.quiz_service import get_or_create_submission, save_answer
            sub_se = get_or_create_submission(sess_id, self.t_a1_id)
            questions = db.session.scalars(
                db.select(Question).where(Question.question_set_id == self.qs_se_id).order_by(Question.order_number.asc())
            ).all()
            save_answer(sub_se, questions[0].id, "A")
            save_answer(sub_se, questions[1].id, "B")

        res_submit = self.client.post("/participant/quiz/submit", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(res_submit.status_code, 200)

        # Check score table and leaderboard
        with self.app.app_context():
            score = db.session.scalar(
                db.select(Score).join(Submission).where(Submission.team_id == self.t_a1_id)
            )
            self.assertIsNotNone(score)
            self.assertEqual(score.raw_score, 50.0)
            self.assertGreaterEqual(score.final_score, 50.0)

            lb = get_session_leaderboard(sess_id)
            self.assertEqual(len(lb["ranked_rows"]), 1)
            self.assertEqual(lb["ranked_rows"][0]["raw_score"], 50.0)
            self.assertGreaterEqual(lb["ranked_rows"][0]["final_score"], 50.0)

    # =========================================================================
    # TEST 17: Admin Station Selection Hub & Context Segregation
    # =========================================================================
    def test_17_admin_station_hub_and_segregation(self):
        self.login_admin(self.client)

        # 1. Access Station Selection Hub
        hub_res = self.client.get("/admin/station-select")
        self.assertEqual(hub_res.status_code, 200)
        hub_html = hub_res.data.decode("utf-8")
        self.assertIn("Pilih Pos Lomba", hub_html)
        self.assertIn("Pos Hardware", hub_html)
        self.assertIn("Pos Software Engineering", hub_html)

        # 2. Select Pos Hardware
        set_hw_res = self.client.get(f"/admin/set-station/{self.st_hw_id}", follow_redirects=True)
        self.assertEqual(set_hw_res.status_code, 200)
        hw_dash_html = set_hw_res.data.decode("utf-8")
        self.assertIn("POS: HARDWARE", hw_dash_html)
        self.assertIn("Verifikasi Hardware", hw_dash_html)
        # Bank Soal should be segregated/hidden when Hardware is active
        self.assertNotIn("Bank Soal (Kuis PG)", hw_dash_html)

        # 3. Select Pos Software Engineering
        set_se_res = self.client.get(f"/admin/set-station/{self.st_se_id}", follow_redirects=True)
        self.assertEqual(set_se_res.status_code, 200)
        se_dash_html = set_se_res.data.decode("utf-8")
        self.assertIn("POS: SOFTWARE ENGINEERING", se_dash_html)
        self.assertIn("Bank Soal (Kuis PG)", se_dash_html)
        # Verifikasi Hardware should be segregated/hidden when Software Eng is active
        self.assertNotIn("🛠️ Verifikasi Hardware", se_dash_html)

        # 4. Return to Global Mode
        set_global_res = self.client.get("/admin/set-station/0", follow_redirects=True)
        self.assertEqual(set_global_res.status_code, 200)
        global_dash_html = set_global_res.data.decode("utf-8")
        self.assertIn("MODE: SEMUA POS", global_dash_html)


if __name__ == "__main__":
    unittest.main()
