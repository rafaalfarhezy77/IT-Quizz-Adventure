import json
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
    MappingStrategy,
    NetworkingSubmission,
    NetworkingSubmissionAudit,
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
from services.networking_service import (
    normalize_text_answer,
    evaluate_short_text_answer,
    get_or_create_networking_submission,
    get_stage_questions,
    get_stage_timer_info,
    save_networking_answer,
    submit_stage,
    get_facilitator_review_queue,
    review_answer_by_facilitator,
    finalize_networking_submission,
    facilitator_control_action,
)
from services.session_service import get_server_now
from services.leaderboard_service import get_session_leaderboard


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    PARTICIPANT_ACCESS_CODE = "QUEST2026"
    SECRET_KEY = "test-key-net-module"
    TIME_BONUS_PER_SECOND = 0.5


class NetworkingModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # 1. Admin
            admin = Admin(
                username="admin_net",
                password_hash=generate_password_hash("Secret123!"),
                is_active=True,
            )
            db.session.add(admin)

            # 2. Stations
            st_net = Station(name="Networking", mode=StationMode.NORMAL, is_active=True)
            st_se = Station(name="Software Engineering", mode=StationMode.MEMBER_ROTATION, is_active=True)
            st_hw = Station(name="Hardware", mode=StationMode.NORMAL, is_active=True)
            db.session.add_all([st_net, st_se, st_hw])
            db.session.flush()

            # 3. Groups A, B, C, D
            grp_a = Group(code="A")
            grp_b = Group(code="B")
            grp_c = Group(code="C")
            grp_d = Group(code="D")
            db.session.add_all([grp_a, grp_b, grp_c, grp_d])
            db.session.flush()

            # 4. Teams in Group A (4 concurrent teams)
            teams_a = []
            for i in range(1, 5):
                t = Team(
                    team_code=f"A-0{i}",
                    team_name=f"Garuda Net 0{i}",
                    school=f"SMK Telkom {i}",
                    group_id=grp_a.id,
                    is_active=True,
                )
                db.session.add(t)
                teams_a.append(t)

            # Teams for Group B, C, D
            team_b = Team(team_code="B-01", team_name="Nexus Net", school="SMK 2", group_id=grp_b.id, is_active=True)
            team_c = Team(team_code="C-01", team_name="Cisco Squad", school="SMA 3", group_id=grp_c.id, is_active=True)
            team_d = Team(team_code="D-01", team_name="Mikrotik Mania", school="SMA 4", group_id=grp_d.id, is_active=True)
            db.session.add_all([team_b, team_c, team_d])
            db.session.flush()

            # 5. Question Sets for Networking (A, B, C, D)
            qs_net_a = QuestionSet(station_id=st_net.id, code="A", name="Set A Networking", status=QuestionSetStatus.READY)
            qs_net_b = QuestionSet(station_id=st_net.id, code="B", name="Set B Networking", status=QuestionSetStatus.READY)
            qs_net_c = QuestionSet(station_id=st_net.id, code="C", name="Set C Networking", status=QuestionSetStatus.READY)
            qs_net_d = QuestionSet(station_id=st_net.id, code="D", name="Set D Networking", status=QuestionSetStatus.READY)
            db.session.add_all([qs_net_a, qs_net_b, qs_net_c, qs_net_d])
            db.session.flush()

            # Seed Set A Questions: 10 MC (A-E), 10 True/False, 5 Short Text
            self._seed_networking_set(qs_net_a.id)
            self._seed_networking_set(qs_net_b.id)

            # 6. Session for Group A (Rotasi 1)
            session_a = CompetitionSession(
                station_id=st_net.id,
                group_id=grp_a.id,
                question_set_id=qs_net_a.id,
                rotation_number=1,
                status=SessionStatus.WAITING,
                duration_seconds=2100,
            )
            db.session.add(session_a)
            db.session.commit()

            # Store IDs to avoid DetachedInstanceError across contexts
            self.admin_id = admin.id
            self.st_net_id = st_net.id
            self.st_se_id = st_se.id
            self.st_hw_id = st_hw.id
            self.grp_a_id = grp_a.id
            self.grp_b_id = grp_b.id
            self.teams_a_ids = [t.id for t in teams_a]
            self.team_b_id = team_b.id
            self.qs_net_a_id = qs_net_a.id
            self.qs_net_b_id = qs_net_b.id
            self.session_a_id = session_a.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _seed_networking_set(self, set_id: int):
        # Stage 1: 10 MC questions (some with A-E)
        for i in range(1, 11):
            q = Question(
                question_set_id=set_id,
                order_number=i,
                stage=1,
                question_type="multiple_choice",
                text=f"Soal Stage 1 No {i}: Apa fungsi router?",
                option_a="Menghubungkan network berbeda",
                option_b="Memperkuat sinyal",
                option_c="Menyaring frame MAC",
                option_d="Mengubah domain name",
                option_e="Menyimpan file statis" if i % 2 == 0 else None,
                correct_answer="A" if i % 2 != 0 else "E",
                is_active=True,
            )
            db.session.add(q)

        # Stage 2: 10 True/False questions
        for i in range(1, 11):
            order = 10 + i
            is_true = (i % 2 == 1)
            q = Question(
                question_set_id=set_id,
                order_number=order,
                stage=2,
                question_type="true_false",
                case_study=f"Studi kasus mini no {i}: Sebuah subnet /24 menggunakan mask 255.255.255.0." if i <= 3 else None,
                text=f"Pernyataan Stage 2 No {i}: Switch layer 2 bekerja pada Data Link Layer." if is_true else f"Pernyataan Stage 2 No {i}: Hub membagi collision domain secara independen.",
                correct_answer="True" if is_true else "False",
                is_active=True,
            )
            db.session.add(q)

        # Stage 3: 5 Short Text questions with accepted answers
        accepted_dict = {
            1: ["access point", "ap", "access point wifi", "pemancar wifi"],
            2: ["dhcp", "dhcp server", "dynamic host configuration protocol"],
            3: ["firewall", "packet filtering firewall", "next generation firewall"],
            4: ["vlan", "virtual lan", "virtual local area network"],
            5: ["dns", "domain name system", "dns server"],
        }
        for i in range(1, 6):
            order = 20 + i
            q = Question(
                question_set_id=set_id,
                order_number=order,
                stage=3,
                question_type="short_text",
                case_study=f"Kantor Cabang XYZ membutuhkan perangkat wireless untuk 50 klien pada lantai 2.",
                text=f"Pertanyaan Stage 3 No {i}: Sebutkan perangkat jaringan yang paling tepat untuk kebutuhan tersebut!",
                accepted_answers=accepted_dict[i],
                correct_answer=accepted_dict[i][0],
                is_active=True,
            )
            db.session.add(q)
        db.session.flush()

    def test_01_concurrent_teams_in_lobby_and_quiz(self):
        """1. Empat tim masuk ke Pos Networking secara bersamaan."""
        with self.app.app_context():
            session_a = db.session.get(CompetitionSession, self.session_a_id)
            session_a.status = SessionStatus.RUNNING
            session_a.started_at = get_server_now()
            db.session.commit()

            subs = []
            # Each of the 4 teams enters
            for i, team_id in enumerate(self.teams_a_ids):
                token = f"client-token-team-{i+1}"
                sub, net_sub, conflict = get_or_create_networking_submission(self.session_a_id, team_id, client_token=token)
                self.assertFalse(conflict)
                self.assertIsNotNone(net_sub)
                self.assertEqual(net_sub.current_stage, 1)
                self.assertEqual(net_sub.session_token, token)
                subs.append(net_sub)

            self.assertEqual(len(subs), 4)
            sub_ids = [s.id for s in subs]
            self.assertEqual(len(set(sub_ids)), 4, "Setiap tim harus memiliki record submission sendiri")

            for s in subs:
                self.assertEqual(s.submission.session.question_set_id, self.qs_net_a_id)

    def test_02_idempotent_session_start(self):
        """2. Fasilitator memulai sesi hanya satu kali meskipun tombol diklik berulang."""
        with self.app.app_context():
            # First start call
            ok1, msg1 = facilitator_control_action(
                session_id=self.session_a_id,
                action="START_SESSION",
                admin_id=self.admin_id,
                reason="Memulai sesi rotasi 1",
            )
            self.assertTrue(ok1)

            session_db = db.session.get(CompetitionSession, self.session_a_id)
            self.assertEqual(session_db.status, SessionStatus.RUNNING)
            first_started_at = session_db.started_at

            # Second start call (duplicate click)
            ok2, msg2 = facilitator_control_action(
                session_id=self.session_a_id,
                action="START_SESSION",
                admin_id=self.admin_id,
                reason="Memulai sesi rotasi 1 (klik kedua)",
            )
            self.assertTrue(ok2)
            session_db2 = db.session.get(CompetitionSession, self.session_a_id)
            self.assertEqual(session_db2.started_at, first_started_at, "Timer tidak boleh ter-reset pada klik ganda")

    def test_03_question_set_matches_group(self):
        """3. Set soal yang diperoleh sesuai kelompok (Kelompok A dapat Set A, B dapat Set B, dst)."""
        with self.app.app_context():
            session_b = CompetitionSession(
                station_id=self.st_net_id,
                group_id=self.grp_b_id,
                question_set_id=self.qs_net_b_id,
                rotation_number=1,
                status=SessionStatus.RUNNING,
                started_at=get_server_now(),
                duration_seconds=2100,
            )
            db.session.add(session_b)
            db.session.commit()

            sub_a, net_sub_a, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            sub_b, net_sub_b, _ = get_or_create_networking_submission(session_b.id, self.team_b_id, "token-b")

            sess_a = db.session.get(CompetitionSession, self.session_a_id)
            q_stage1_a = get_stage_questions(sess_a, 1)
            q_stage1_b = get_stage_questions(session_b, 1)

            self.assertEqual(q_stage1_a[0].question_set_id, self.qs_net_a_id)
            self.assertEqual(q_stage1_b[0].question_set_id, self.qs_net_b_id)
            self.assertNotEqual(q_stage1_a[0].question_set_id, q_stage1_b[0].question_set_id)

    def test_04_cross_set_access_prevention(self):
        """4. Peserta tidak dapat mengakses set kelompok lain."""
        with self.app.app_context():
            sub_a, net_sub_a, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            q_in_set_b = db.session.scalar(
                db.select(Question).where(Question.question_set_id == self.qs_net_b_id)
            )

            ok, err, status = save_networking_answer(net_sub_a.submission_id, q_in_set_b.id, "A")
            self.assertFalse(ok, "Jawaban untuk soal dari set lain harus ditolak")
            self.assertIn("tidak termasuk dalam paket soal", err)

    def test_05_multiple_choice_a_to_e_saved_and_graded(self):
        """5. Pilihan ganda A–E dapat disimpan dan dinilai."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            q_e = db.session.scalar(
                db.select(Question).where(
                    Question.question_set_id == self.qs_net_a_id,
                    Question.stage == 1,
                    Question.correct_answer == "E",
                )
            )
            self.assertIsNotNone(q_e)
            self.assertEqual(q_e.option_e, "Menyimpan file statis")

            first_question = get_stage_questions(sub.session, 1)[0]
            self.assertTrue(save_networking_answer(sub.id, first_question.id, first_question.correct_answer)[0])
            ok, err, status = save_networking_answer(net_sub.submission_id, q_e.id, "E")
            self.assertTrue(ok)

            ans = db.session.scalar(
                db.select(Answer).where(
                    Answer.submission_id == net_sub.submission_id,
                    Answer.question_id == q_e.id,
                )
            )
            self.assertEqual(ans.selected_answer, "E")
            self.assertTrue(ans.is_correct)
            self.assertEqual(ans.points_awarded, float(q_e.weight))

    def test_06_true_false_graded(self):
        """6. Soal benar–salah dapat dinilai."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            net_sub.current_stage = 2
            net_sub.stage_2_started_at = get_server_now()
            db.session.commit()

            q_tf = db.session.scalar(
                db.select(Question).where(
                    Question.question_set_id == self.qs_net_a_id,
                    Question.stage == 2,
                    Question.correct_answer == "True",
                )
            )
            ok, err, status = save_networking_answer(net_sub.submission_id, q_tf.id, "Benar")
            self.assertTrue(ok)

            ans = db.session.scalar(
                db.select(Answer).where(
                    Answer.submission_id == net_sub.submission_id,
                    Answer.question_id == q_tf.id,
                )
            )
            self.assertTrue(ans.is_correct)

            ok_w, err_w, status_w = save_networking_answer(net_sub.submission_id, q_tf.id, "Salah")
            self.assertFalse(ok_w)
            ans_w = db.session.scalar(
                db.select(Answer).where(
                    Answer.submission_id == net_sub.submission_id,
                    Answer.question_id == q_tf.id,
                )
            )
            self.assertTrue(ans_w.is_correct)

    def test_07_short_text_variations_normalization(self):
        """7. Variasi jawaban isian dikenali setelah normalisasi."""
        self.assertEqual(normalize_text_answer("  Access   Point  "), "access point")
        self.assertEqual(normalize_text_answer("Access-Point!"), "access-point!")
        self.assertEqual(normalize_text_answer("D.H.C.P. Server"), "d.h.c.p. server")

        accepted = ["access point", "ap", "access point wifi", "pemancar wifi"]
        is_corr, status = evaluate_short_text_answer("  ACCESS POINT  ", accepted)
        self.assertTrue(is_corr)
        self.assertEqual(status, "AUTO_GRADED")

        is_corr, status = evaluate_short_text_answer("AP", accepted)
        self.assertTrue(is_corr)
        self.assertEqual(status, "AUTO_GRADED")

        is_corr, status = evaluate_short_text_answer("Pemancar Wifi", accepted)
        self.assertTrue(is_corr)
        self.assertEqual(status, "AUTO_GRADED")

    def test_08_unrecognized_short_text_needs_review(self):
        """8. Jawaban tidak dikenal masuk antrean verifikasi."""
        accepted = ["access point", "ap", "access point wifi", "pemancar wifi"]
        is_corr, status = evaluate_short_text_answer("pemancar sinyal radio lokal", accepted)
        self.assertFalse(is_corr)
        self.assertEqual(status, "NEEDS_REVIEW")

        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            net_sub.current_stage = 3
            net_sub.stage_3_started_at = get_server_now()
            db.session.commit()

            q3 = db.session.scalar(
                db.select(Question).where(
                    Question.question_set_id == self.qs_net_a_id,
                    Question.stage == 3,
                )
            )
            ok, err, status = save_networking_answer(net_sub.submission_id, q3.id, "pemancar sinyal radio lokal")
            self.assertTrue(ok)
            self.assertEqual(status, "NEEDS_REVIEW")

            queue = get_facilitator_review_queue(self.session_a_id)
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0]["user_answer"], "pemancar sinyal radio lokal")

    def test_09_refresh_does_not_reset_timer(self):
        """9. Refresh tidak mengulang timer."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            fixed_start = get_server_now() - timedelta(seconds=60)
            net_sub.stage_1_started_at = fixed_start
            net_sub.stage_1_duration_seconds = 300
            db.session.commit()

            timer1 = get_stage_timer_info(net_sub, 1)
            self.assertAlmostEqual(timer1["remaining_seconds"], 240, delta=2)

            sub_reloaded = db.session.get(NetworkingSubmission, net_sub.id)
            self.assertEqual(sub_reloaded.stage_1_started_at, fixed_start, "Waktu mulai tidak boleh berubah saat reload")

    def test_10_disconnect_reconnect_preserves_answers(self):
        """10. Koneksi terputus tidak menghapus jawaban."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            q1 = db.session.scalar(
                db.select(Question).where(Question.question_set_id == self.qs_net_a_id, Question.stage == 1)
            )
            save_networking_answer(net_sub.submission_id, q1.id, "A")

            # Disconnect and reconnect
            sub_after, net_sub_after, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            saved_ans = db.session.scalar(
                db.select(Answer).where(Answer.submission_id == net_sub_after.submission_id, Answer.question_id == q1.id)
            )
            self.assertIsNotNone(saved_ans)
            self.assertEqual(saved_ans.selected_answer, "A")

    def test_11_timeout_causes_autosubmit(self):
        """11. Waktu habis menyebabkan autosubmit."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            net_sub.stage_1_started_at = get_server_now() - timedelta(seconds=610)
            db.session.commit()

            timer = get_stage_timer_info(net_sub, 1)
            self.assertTrue(timer["is_expired"])
            self.assertEqual(timer["remaining_seconds"], 0)

            ok, err, next_stage = submit_stage(net_sub.submission_id, 1, is_timeout=True)
            self.assertTrue(ok)
            self.assertEqual(next_stage, 2)

            sub_updated = db.session.get(NetworkingSubmission, net_sub.id)
            self.assertEqual(sub_updated.current_stage, 2)
            self.assertIsNotNone(sub_updated.stage_1_submitted_at)

    def test_12_completed_stage_cannot_be_edited(self):
        """12. Tahap yang telah selesai tidak dapat diedit kembali."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            q1 = db.session.scalar(
                db.select(Question).where(Question.question_set_id == self.qs_net_a_id, Question.stage == 1)
            )
            save_networking_answer(net_sub.submission_id, q1.id, "A")

            submit_stage(net_sub.submission_id, 1, is_timeout=False)

            ok, err, status = save_networking_answer(net_sub.submission_id, q1.id, "B")
            self.assertFalse(ok)
            self.assertIn("terkunci", err)

    def test_13_stamp_awarded_when_stage3_ge_4(self):
        """13. Stamp diberikan ketika Tahap 3 benar minimal 4."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            net_sub.current_stage = 3
            net_sub.stage_3_started_at = get_server_now()
            db.session.commit()

            q_stage3 = db.session.scalars(
                db.select(Question).where(Question.question_set_id == self.qs_net_a_id, Question.stage == 3).order_by(Question.order_number)
            ).all()
            self.assertEqual(len(q_stage3), 5)

            for i, q in enumerate(q_stage3):
                if i < 4:
                    save_networking_answer(net_sub.submission_id, q.id, q.accepted_answers[0])
                else:
                    save_networking_answer(net_sub.submission_id, q.id, "jawaban asal-asalan")

            ok_sub, _, _ = submit_stage(net_sub.submission_id, 3, is_timeout=False)
            self.assertTrue(ok_sub)

            ok_fin, _, data = finalize_networking_submission(net_sub.id, self.admin_id, notes="Verifikasi tuntas")
            self.assertTrue(ok_fin)
            self.assertTrue(data["has_stamp"], "Tim dengan 4/5 benar di Tahap 3 harus mendapatkan Stamp")

            sub_fin = db.session.get(NetworkingSubmission, net_sub.id)
            self.assertTrue(sub_fin.has_stamp)
            self.assertEqual(sub_fin.stage_3_correct_count, 4)

    def test_14_stamp_denied_when_stage3_lt_4(self):
        """14. Stamp tidak diberikan ketika Tahap 3 benar kurang dari 4."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[1], "token-a2")
            net_sub.current_stage = 3
            net_sub.stage_3_started_at = get_server_now()
            db.session.commit()

            q_stage3 = db.session.scalars(
                db.select(Question).where(Question.question_set_id == self.qs_net_a_id, Question.stage == 3).order_by(Question.order_number)
            ).all()

            for i, q in enumerate(q_stage3):
                if i < 3:
                    save_networking_answer(net_sub.submission_id, q.id, q.accepted_answers[0])
                else:
                    save_networking_answer(net_sub.submission_id, q.id, "jawaban salah")

            submit_stage(net_sub.submission_id, 3, is_timeout=False)
            ok_fin, _, data = finalize_networking_submission(net_sub.id, self.admin_id, notes="Verifikasi tuntas")
            self.assertFalse(data["has_stamp"], "Tim dengan 3/5 benar di Tahap 3 TIDAK boleh mendapatkan Stamp")

            sub_fin = db.session.get(NetworkingSubmission, net_sub.id)
            self.assertFalse(sub_fin.has_stamp)
            self.assertEqual(sub_fin.stage_3_correct_count, 3)

    def test_15_finalization_is_idempotent_no_duplicate_scores(self):
        """15. Finalisasi tidak menggandakan skor."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")
            net_sub.current_stage = 3
            net_sub.stage_3_started_at = get_server_now()
            db.session.commit()

            submit_stage(net_sub.submission_id, 3, is_timeout=False)

            # First finalization
            ok1, _, data1 = finalize_networking_submission(net_sub.id, self.admin_id, notes="Finalisasi ke-1")
            self.assertTrue(ok1)
            first_final_score = data1["final_score"]

            score_records_1 = db.session.scalars(
                db.select(Score).where(Score.submission_id == net_sub.submission_id)
            ).all()
            self.assertEqual(len(score_records_1), 1)

            # Second finalization (re-request)
            ok2, _, data2 = finalize_networking_submission(net_sub.id, self.admin_id, notes="Finalisasi ke-2")
            score_records_2 = db.session.scalars(
                db.select(Score).where(Score.submission_id == net_sub.submission_id)
            ).all()
            self.assertEqual(len(score_records_2), 1, "Tidak boleh ada duplikasi row Score")
            self.assertEqual(score_records_2[0].final_score, first_final_score)

    def test_16_other_stations_unaffected(self):
        """16. Pos lain tetap berjalan seperti sebelumnya."""
        with self.app.app_context():
            st_se = db.session.get(Station, self.st_se_id)
            self.assertEqual(st_se.mode, StationMode.MEMBER_ROTATION)

            st_hw = db.session.get(Station, self.st_hw_id)
            self.assertEqual(st_hw.name, "Hardware")

            st_net = db.session.get(Station, self.st_net_id)
            self.assertEqual(st_net.name, "Networking")

    def test_17_leaderboard_only_finalized_results(self):
        """17. Leaderboard hanya memakai hasil yang sudah difinalisasi."""
        with self.app.app_context():
            # Sub 1 finalized
            sub1, net_sub1, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a1")
            net_sub1.current_stage = 3
            net_sub1.stage_1_score = 100
            net_sub1.stage_2_score = 100
            net_sub1.stage_3_score = 50
            db.session.commit()
            submit_stage(net_sub1.submission_id, 3, is_timeout=False)
            finalize_networking_submission(net_sub1.id, self.admin_id)

            # Sub 2 submitted but NOT finalized yet
            sub2, net_sub2, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[1], "token-a2")
            net_sub2.current_stage = 3
            net_sub2.stage_1_score = 90
            db.session.commit()
            submit_stage(net_sub2.submission_id, 3, is_timeout=False)

            leaderboard = get_session_leaderboard(self.session_a_id)
            ranked_team_ids = [row["team_id"] for row in leaderboard["ranked_rows"]]

            self.assertIn(self.teams_a_ids[0], ranked_team_ids)
            self.assertNotIn(self.teams_a_ids[1], ranked_team_ids, "Tim yang belum difinalisasi tidak boleh masuk leaderboard resmi")

    def test_18_facilitator_controls_and_audit_log(self):
        """18. Kontrol fasilitator mewajibkan alasan dan tercatat dalam audit log."""
        with self.app.app_context():
            sub, net_sub, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0], "token-a")

            # Action without reason should fail
            ok_fail, msg_fail = facilitator_control_action(
                session_id=self.session_a_id,
                action="ADD_TIME",
                admin_id=self.admin_id,
                reason="",  # empty reason
                team_id=self.teams_a_ids[0],
            )
            self.assertFalse(ok_fail)
            self.assertIn("Alasan", msg_fail)

            # Action with reason succeeds and creates audit log
            ok_add_time, msg_add = facilitator_control_action(
                session_id=self.session_a_id,
                action="ADD_TIME",
                admin_id=self.admin_id,
                reason="Gangguan kabel LAN lokal selama 2 menit",
                team_id=self.teams_a_ids[0],
                extra_seconds=120,
            )
            self.assertTrue(ok_add_time)

            audit = db.session.scalar(
                db.select(NetworkingSubmissionAudit).where(
                    NetworkingSubmissionAudit.networking_submission_id == net_sub.id,
                    NetworkingSubmissionAudit.action == "ADD_TIME_STAGE_1",
                )
            )
            self.assertIsNotNone(audit)
            self.assertEqual(audit.reason, "Gangguan kabel LAN lokal selama 2 menit")
            self.assertEqual(audit.admin_id, self.admin_id)

    def _load_source_bank(self):
        from pathlib import Path
        from services.question_json_import import parse_and_validate_question_json, execute_question_import, get_temp_upload_dir
        import uuid
        for qs in db.session.scalars(db.select(QuestionSet).where(QuestionSet.station_id == self.st_net_id)).all():
            for q in list(qs.questions):
                db.session.delete(q)
        db.session.commit()
        token = uuid.uuid4().hex
        path = get_temp_upload_dir() / (token + ".json")
        path.write_bytes(Path("bank_soal_networking.json").read_bytes())
        validation = parse_and_validate_question_json(path, self.st_net_id)
        self.assertTrue(validation["is_valid"], str(validation))
        self.assertEqual(validation["total_questions"], 100)
        ok, result, error = execute_question_import(token, self.st_net_id)
        self.assertTrue(ok, error)
        self.assertEqual(result["inserted"], 100)
        from services.networking_question_import import flatten_networking_set
        return flatten_networking_set(json.loads(Path("bank_soal_networking.json").read_text(encoding="utf-8"))["sets"]["A"])[0]

    def test_19_source_bank_ready_locked_and_exact_weights(self):
        from pathlib import Path
        from services.question_service import validate_question_set_ready
        from services.question_json_import import parse_and_validate_question_json
        with self.app.app_context():
            bank = self._load_source_bank()
            self.assertEqual(sum(q["weight"] for q in bank), 100)
            self.assertEqual(bank[17]["correct_answer"], "Salah")
            self.assertIn("20 komputer", bank[17]["case_study"])
            self.assertIn("Bluetooth", bank[18]["case_study"])
            qs = db.session.get(QuestionSet, self.qs_net_a_id)
            self.assertTrue(validate_question_set_ready(qs)[0])
            qs.status = QuestionSetStatus.LOCKED
            db.session.commit()
            self.assertFalse(parse_and_validate_question_json(Path("bank_soal_networking.json"), self.st_net_id, "UPDATE")["is_valid"])

    def test_20_four_clients_complete_with_id_collision_and_one_bonus(self):
        from services.session_service import get_remaining_seconds
        with self.app.app_context():
            bank = self._load_source_bank()
            # Offset base submission IDs to reproduce the former ambiguous OR lookup.
            dummy = Submission(session_id=self.session_a_id, team_id=self.team_b_id, status=SubmissionStatus.IN_PROGRESS)
            db.session.add(dummy)
            db.session.commit()
            facilitator_control_action(self.session_a_id, "START_SESSION", self.admin_id, "Mulai bersama")
            clients = []
            for team_id in self.teams_a_ids:
                client = self.app.test_client()
                with client.session_transaction() as cookie:
                    cookie.update(participant_authorized=True, participant_station_id=self.st_net_id, participant_group_id=self.grp_a_id, participant_team_id=team_id, participant_confirmed=True, participant_rules_accepted=True)
                clients.append(client)
            questions = db.session.scalars(db.select(Question).where(Question.question_set_id == self.qs_net_a_id).order_by(Question.order_number)).all()
            for stage in (1, 2, 3):
                for index, client in enumerate(clients):
                    self.assertEqual(client.get("/participant/quiz").status_code, 200)
                    for q in questions:
                        if q.stage != stage:
                            continue
                        answer = q.correct_answer if index == 0 else "A" if stage == 1 else "Benar" if stage == 2 else "salah"
                        response = client.post("/participant/networking/save-answer", json={"question_id":q.id, "answer_value":answer})
                        self.assertTrue(response.json["success"], response.json)
                    response = client.post("/participant/networking/submit-stage", data={"stage_num":stage})
                    self.assertEqual(response.status_code, 302)
                for team_id in self.teams_a_ids:
                    sub = db.session.scalar(db.select(Submission).where(Submission.session_id==self.session_a_id, Submission.team_id==team_id))
                    self.assertEqual(sub.networking_submission.current_stage, stage+1)
            for index, team_id in enumerate(self.teams_a_ids):
                sub = db.session.scalar(db.select(Submission).where(Submission.session_id==self.session_a_id, Submission.team_id==team_id))
                ok, _, result = finalize_networking_submission(sub.networking_submission.id, self.admin_id)
                self.assertTrue(ok)
                self.assertEqual(sub.networking_submission.has_stamp, index == 0)
                if index == 0:
                    self.assertEqual(sub.score.raw_score, 100)
                    expected = get_remaining_seconds(sub.session, sub.submitted_at) * 0.5
                    self.assertEqual(sub.score.time_bonus, expected)
                    self.assertEqual(sub.score.final_score, 100+expected)
                self.assertEqual(clients[index].get("/participant/result").status_code, 200)

    def test_21_safe_normalization_primary_key_and_stale_stage(self):
        self.assertFalse(evaluate_short_text_answer("P.A.N.", ["PAN"])[0])
        self.assertFalse(evaluate_short_text_answer("access-point", ["Access Point"])[0])
        self.assertTrue(evaluate_short_text_answer("  WIDE   AREA NETWORK ", ["Wide Area Network"])[0])
        with self.app.app_context():
            sub, net, _ = get_or_create_networking_submission(self.session_a_id, self.teams_a_ids[0])
            self.assertEqual(net.stage_1_duration_seconds, 600)
            self.assertEqual(net.stage_2_duration_seconds, 300)
            self.assertFalse(submit_stage(sub.id, 2)[0])
            self.assertTrue(submit_stage(sub.id, 1)[0])
            self.assertFalse(submit_stage(sub.id, 1)[0])
            self.assertEqual(net.current_stage, 2)
            self.assertFalse(finalize_networking_submission(net.id, self.admin_id)[0])

    def test_22_legacy_update_and_import_validation(self):
        from pathlib import Path
        import uuid
        from services.question_json_import import execute_question_import, get_temp_upload_dir, parse_and_validate_question_json
        with self.app.app_context():
            token = uuid.uuid4().hex
            path = get_temp_upload_dir() / (token + ".json")
            path.write_bytes(Path("bank_soal_networking.json").read_bytes())
            ok, result, error = execute_question_import(token, self.st_net_id, "UPDATE")
            self.assertTrue(ok, error)
            self.assertEqual(result["updated"], 50)
            self.assertEqual(result["inserted"], 50)
            data = json.loads(Path("bank_soal_networking.json").read_text(encoding="utf-8"))
            data["sets"]["A"]["stages"]["3"][0]["accepted_answers"] = [None, 123]
            data["sets"]["A"]["stages"]["1"][0]["weight"] = 100
            data["sets"]["A"]["stages"]["2"][0]["question_type"] = "multiple_choice"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertFalse(parse_and_validate_question_json(path, self.st_net_id, "UPDATE")["is_valid"])
            path.unlink()

    def test_23_editor_and_preview_preserve_short_text(self):
        with self.app.app_context():
            self._load_source_bank()
            q = db.session.scalar(db.select(Question).where(Question.question_set_id == self.qs_net_a_id, Question.order_number == 25))
            client = self.app.test_client()
            with client.session_transaction() as cookie:
                cookie.update(admin_id=self.admin_id, admin_station_id=self.st_net_id)
            self.assertEqual(client.get(f"/admin/questions/{q.id}/edit").status_code, 200)
            response = client.post(f"/admin/questions/{q.id}/edit", data={"text":q.text,"correct_answer":"Access Point","weight":6,"order_number":25,"stage":3,"question_type":"short_text","accepted_answers_text":"AP\naccess point WiFi\npemancar WiFi", "case_study":"Studi kasus tetap"})
            self.assertEqual(response.status_code, 302)
            db.session.refresh(q)
            self.assertEqual(q.accepted_answers, ["AP", "access point WiFi", "pemancar WiFi"])
            for suffix in ("", "/preview"):
                self.assertEqual(client.get(f"/admin/questions/set/{self.qs_net_a_id}"+suffix).status_code, 200)

    def test_24_expired_timer_server_transition_and_reject_edit(self):
        with self.app.app_context():
            facilitator_control_action(self.session_a_id, "START_SESSION", self.admin_id, "Timer test")
            sub = db.session.scalar(db.select(Submission).where(Submission.team_id==self.teams_a_ids[0], Submission.session_id==self.session_a_id))
            net = sub.networking_submission
            net.stage_1_started_at = get_server_now()-timedelta(seconds=601)
            db.session.commit()
            q = get_stage_questions(sub.session, 1)[0]
            self.assertFalse(save_networking_answer(sub.id,q.id,"A")[0])
            client = self.app.test_client()
            with client.session_transaction() as cookie:
                cookie.update(participant_authorized=True, participant_station_id=self.st_net_id, participant_group_id=self.grp_a_id, participant_team_id=self.teams_a_ids[0], participant_confirmed=True, participant_rules_accepted=True)
            self.assertEqual(client.get("/participant/quiz").status_code, 302)
            db.session.refresh(net)
            self.assertEqual(net.current_stage, 2)
            self.assertFalse(submit_stage(sub.id, 1)[0])

    def test_25_primary_answer_and_bonus_idempotence(self):
        with self.app.app_context():
            self._load_source_bank()
            facilitator_control_action(self.session_a_id,"START_SESSION",self.admin_id,"Mulai test")
            sub = db.session.scalar(db.select(Submission).where(Submission.team_id==self.teams_a_ids[0],Submission.session_id==self.session_a_id))
            net = sub.networking_submission
            net.current_stage=3
            net.stage_3_started_at=get_server_now()
            q=get_stage_questions(sub.session,3)[0]
            q.accepted_answers=["Personal Area Network"]
            db.session.commit()
            self.assertTrue(save_networking_answer(sub.id,q.id,"  pan ")[0])
            self.assertTrue(submit_stage(sub.id,3)[0])
            self.assertTrue(finalize_networking_submission(net.id,self.admin_id)[0])
            first=net.final_score
            self.assertTrue(finalize_networking_submission(net.id,self.admin_id,time_bonus=99999)[0])
            self.assertEqual(net.final_score,first)
            self.assertEqual(sub.score.final_score,first)

    def test_26_facilitator_http_lobby_start_review_finalize(self):
        with self.app.app_context():
            self._load_source_bank()
            db.session.delete(db.session.get(CompetitionSession,self.session_a_id))
            db.session.commit()
            admin=self.app.test_client()
            with admin.session_transaction() as cookie:
                cookie.update(admin_id=self.admin_id,admin_station_id=self.st_net_id)
            response=admin.post("/admin/networking/open-lobby",data={"group_id":self.grp_a_id,"rotation":3,"set_id":self.qs_net_a_id})
            self.assertEqual(response.status_code,302)
            competition=db.session.scalar(db.select(CompetitionSession).where(CompetitionSession.group_id==self.grp_a_id))
            self.assertEqual(competition.duration_seconds,2100)
            self.assertEqual(admin.post("/admin/networking/control",data={"session_id":competition.id,"action":"START_SESSION","reason":"Mulai empat tim"}).status_code,302)
            self.assertEqual(admin.get(f"/admin/networking/monitor/{competition.id}").status_code,200)
            subs=db.session.scalars(db.select(Submission).where(Submission.session_id==competition.id)).all()
            self.assertEqual(len(subs),4)
            for sub in subs:
                for stage in (1,2,3):
                    self.assertTrue(submit_stage(sub.id,stage)[0])
            frozen=subs[0].networking_submission.time_bonus
            competition.status=SessionStatus.FINISHED
            db.session.commit()
            self.assertEqual(admin.get(f"/admin/networking/verify/{competition.id}").status_code,200)
            self.assertEqual(admin.post(f"/admin/networking/finalize-session/{competition.id}").status_code,302)
            db.session.refresh(subs[0].networking_submission)
            self.assertEqual(subs[0].networking_submission.verification_status,"FINALIZED")
            self.assertEqual(subs[0].score.time_bonus,frozen)
            self.assertEqual(admin.get("/admin/questions/sample.json?station=networking").json["pos"],"Networking")

    def test_27_networking_import_ui_upload_preview_confirm(self):
        import io, re
        from pathlib import Path
        with self.app.app_context():
            client=self.app.test_client()
            with client.session_transaction() as cookie:
                cookie.update(admin_id=self.admin_id,admin_station_id=self.st_net_id)
            page=client.get("/admin/questions/import")
            text=page.get_data(as_text=True)
            self.assertEqual(page.status_code,200)
            self.assertIn("Import Soal Networking",text)
            self.assertIn("Isian singkat",text)
            self.assertNotIn("Pembagian Anggota Tim",text)
            self.assertNotIn("Soal 1–3: Anggota 1",text)
            sample=client.get("/admin/questions/sample.json")
            self.assertEqual(sample.json["pos"],"Networking")
            self.assertEqual(set(sample.json["sets"]["A"]["stages"]),{"1","2","3"})
            preview=client.post("/admin/questions/import",data={"station_id":self.st_net_id,"mode":"UPDATE","file":(io.BytesIO(Path("bank_soal_networking.json").read_bytes()),"networking.json")},content_type="multipart/form-data")
            text=preview.get_data(as_text=True)
            self.assertEqual(preview.status_code,200)
            self.assertIn("Preview Import Networking",text)
            self.assertIn("True or Trap",text)
            self.assertIn("Personal Area Network",text)
            self.assertNotIn("Distribusi Giliran Anggota",text)
            token=re.search(r'name="file_token"[^>]*value="([a-z0-9]+)"',text).group(1)
            response=client.post("/admin/questions/import/confirm",data={"file_token":token,"station_id":self.st_net_id,"mode":"UPDATE"})
            self.assertEqual(response.status_code,302)
            qs=db.session.get(QuestionSet,self.qs_net_a_id)
            self.assertEqual(len(qs.questions),25)
            self.assertEqual(sum(q.weight for q in qs.questions),100)
            self.assertTrue(all(q.member_number is None for q in qs.questions))
            self.assertEqual(len([q for q in qs.questions if q.question_type=="true_false"]),10)
            self.assertEqual(len([q for q in qs.questions if q.question_type=="short_text"]),5)
            index=client.get("/admin/questions")
            self.assertNotIn("+ TAMBAH STUDY CASE",index.get_data(as_text=True))

    def test_28_global_admin_selects_matching_import_and_editor(self):
        with self.app.app_context():
            self._load_source_bank()
            client=self.app.test_client()
            with client.session_transaction() as cookie:cookie.update(admin_id=self.admin_id,admin_station_id=0)
            net=client.get(f"/admin/questions/import?station_id={self.st_net_id}").get_data(as_text=True)
            software=client.get(f"/admin/questions/import?station_id={self.st_se_id}").get_data(as_text=True)
            self.assertIn("Import Soal Networking",net)
            self.assertNotIn("Pembagian Anggota Tim",net)
            self.assertIn("Pembagian Anggota Tim",software)
            for stage,order in [(1,1),(2,11),(3,21)]:
                q=db.session.scalar(db.select(Question).where(Question.question_set_id==self.qs_net_a_id,Question.order_number==order))
                page=client.get(f"/admin/questions/{q.id}/edit")
                self.assertEqual(page.status_code,200)
                self.assertIn('id="networking-question-form"',page.get_data(as_text=True))
                self.assertIn('id="networking-key-choice"',page.get_data(as_text=True))

    def test_29_networking_grouped_and_legacy_formats_reject_software_assumptions(self):
        from pathlib import Path
        import tempfile
        from services.networking_question_import import flatten_networking_set
        from services.question_json_import import parse_and_validate_question_json
        with self.app.app_context(), tempfile.TemporaryDirectory() as directory:
            data=json.loads(Path("bank_soal_networking.json").read_text(encoding="utf-8"))
            path=Path(directory)/"bank.json"
            def check(value):
                path.write_text(json.dumps(value),encoding="utf-8")
                return parse_and_validate_question_json(path,self.st_net_id,"UPDATE")
            self.assertTrue(check(data)["is_valid"])
            legacy={"pos":"Networking","sets":{code:flatten_networking_set(value)[0] for code,value in data["sets"].items()}}
            self.assertTrue(check(legacy)["is_valid"])
            data["sets"]["A"]["stages"]["2"][0]["member"]=1
            invalid=check(data)
            self.assertFalse(invalid["is_valid"])
            self.assertTrue(any("member/giliran" in error for q in invalid["questions"] for error in q["errors"]))
            del data["sets"]["A"]["stages"]["2"][0]["member"]
            del data["sets"]["A"]["stages"]["2"][7]["case_study"]
            self.assertFalse(check(data)["is_valid"])
            data["pos"]="Software Engineering"
            self.assertFalse(check(data)["success"])

    def test_30_choices_are_sequential_immutable_and_retry_safe(self):
        with self.app.app_context():
            facilitator_control_action(self.session_a_id,"START_SESSION",self.admin_id,"Mulai test soal berurutan")
            sub,net,_=get_or_create_networking_submission(self.session_a_id,self.teams_a_ids[0])
            first,second=get_stage_questions(sub.session,1)[:2]
            self.assertFalse(save_networking_answer(sub.id,second.id,"A")[0])
            self.assertTrue(save_networking_answer(sub.id,first.id,"A")[0])
            self.assertTrue(save_networking_answer(sub.id,first.id,"A")[0])
            self.assertFalse(save_networking_answer(sub.id,first.id,"B")[0])
            self.assertTrue(save_networking_answer(sub.id,second.id,"E")[0])
            answer=db.session.scalar(db.select(Answer).where(Answer.submission_id==sub.id,Answer.question_id==first.id))
            self.assertEqual(answer.selected_answer,"A")
            client=self.app.test_client()
            with client.session_transaction() as cookie:
                cookie.update(participant_authorized=True,participant_station_id=self.st_net_id,participant_group_id=self.grp_a_id,participant_team_id=self.teams_a_ids[0],participant_confirmed=True,participant_rules_accepted=True)
            text=client.get("/participant/quiz").get_data(as_text=True)
            import re
            cards=re.findall(r'<div class="net-q-card" id="q-card-([0-9]+)"[^>]*>',text)
            self.assertEqual(len(cards),10)
            third=get_stage_questions(sub.session,1)[2]
            # Inspect attributes directly: only the next unanswered card is visible.
            tags=re.findall(r'<div class="net-q-card" id="q-card-([0-9]+)"([^>]*)>',text)
            self.assertEqual([int(qid) for qid,attrs in tags if "hidden" not in attrs],[third.id])
            self.assertEqual(client.post("/participant/networking/submit-stage",data={"stage_num":1}).status_code,302)
            db.session.refresh(net)
            self.assertEqual(net.current_stage,1)


if __name__ == "__main__":
    unittest.main()
