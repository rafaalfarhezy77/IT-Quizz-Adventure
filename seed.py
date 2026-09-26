import os

from werkzeug.security import generate_password_hash

from app import app
from models import (
    Admin,
    ChallengePackage,
    ChallengeType,
    Group,
    PackageStatus,
    QuestionSet,
    QuestionSetStatus,
    Station,
    StationMode,
    db,
)


def seed_database():
    db.create_all()

    for code in ("A", "B", "C", "D"):
        if not db.session.scalar(db.select(Group).where(Group.code == code)):
            db.session.add(Group(code=code))

    stations = {
        "Software Engineering": StationMode.MEMBER_ROTATION,
        "Cyber Security": StationMode.NORMAL,
        "Hardware": StationMode.BELUM_DIKETAHUI,
        "Networking": StationMode.NORMAL,
    }
    # Hapus stasiun non-aktif yang tidak ada dalam daftar stations
    for old_st in db.session.scalars(db.select(Station)).all():
        if old_st.name not in stations:
            for qs in list(old_st.question_sets):
                for q in list(qs.questions):
                    db.session.delete(q)
                db.session.delete(qs)
            db.session.delete(old_st)

    for name, mode in stations.items():
        station = db.session.scalar(db.select(Station).where(Station.name == name))
        if station is None:
            station = Station(name=name, mode=mode, is_active=True)
            db.session.add(station)
        else:
            station.mode = mode
            station.is_active = True

    username = os.environ.get("DEV_ADMIN_USERNAME", "admin")
    password = os.environ.get("DEV_ADMIN_PASSWORD", "admin123")
    if not db.session.scalar(db.select(Admin).where(Admin.username == username)):
        db.session.add(Admin(username=username, password_hash=generate_password_hash(password)))

    db.session.flush()

    # Seed Question Sets A, B, C, D hanya untuk stasiun aktif yang sudah memiliki konsep/mode pasti
    db_stations = db.session.scalars(
        db.select(Station).where(
            Station.is_active.is_(True),
            Station.mode != StationMode.BELUM_DIKETAHUI,
        )
    ).all()
    for st in db_stations:
        for code in ("A", "B", "C", "D"):
            qs = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == st.id,
                    QuestionSet.code == code,
                )
            )
            if qs is None:
                db.session.add(
                    QuestionSet(
                        station_id=st.id,
                        code=code,
                        name=f"Set {code}",
                        status=QuestionSetStatus.DRAFT,
                    )
                )

    # Seed sample teams jika belum ada
    from models import Team
    if db.session.scalar(db.select(db.func.count()).select_from(Team)) == 0:
        grp_a = db.session.scalar(db.select(Group).where(Group.code == "A"))
        grp_b = db.session.scalar(db.select(Group).where(Group.code == "B"))
        grp_c = db.session.scalar(db.select(Group).where(Group.code == "C"))
        grp_d = db.session.scalar(db.select(Group).where(Group.code == "D"))
        if grp_a and grp_b and grp_c and grp_d:
            db.session.add_all([
                Team(team_code="A01", team_name="Garuda Cyber", school="SMK Negeri 1 Surabaya", group_id=grp_a.id, is_active=True),
                Team(team_code="A02", team_name="Bintang Algoritma", school="SMA Negeri 5 Surabaya", group_id=grp_a.id, is_active=True),
                Team(team_code="B01", team_name="Vektor Nexus", school="SMK Telkom Sidoarjo", group_id=grp_b.id, is_active=True),
                Team(team_code="C01", team_name="Sintaks Juara", school="SMA Katolik St. Louis", group_id=grp_c.id, is_active=True),
                Team(team_code="D01", team_name="Byte Force", school="SMK Negeri 2 Surabaya", group_id=grp_d.id, is_active=True),
            ])

    # Seed sample questions untuk Set A di setiap station aktif jika belum ada soal aktif
    from models import Question
    sample_questions_data = {
        "Software Engineering": [
            ("Manakah dari prinsip SOLID berikut yang menyatakan bahwa sebuah class sebaiknya hanya memiliki satu alasan untuk berubah?", "Single Responsibility Principle", "Open/Closed Principle", "Liskov Substitution Principle", "Dependency Inversion Principle", "A", 1.0),
            ("Struktur data manakah yang bekerja dengan prinsip First-In First-Out (FIFO)?", "Stack", "Queue", "Binary Tree", "Graph", "B", 1.0),
            ("Kompleksitas waktu rata-rata (average time complexity) dari algoritma pencarian Binary Search adalah...", "O(1)", "O(n)", "O(log n)", "O(n^2)", "C", 1.0),
            ("Dalam paradigma OOP, mekanisme menyembunyikan detail implementasi internal dan membatasi akses langsung ke data objek disebut...", "Inheritance", "Encapsulation", "Polymorphism", "Overloading", "B", 1.0),
            ("Perintah Git yang digunakan untuk membatalkan commit terakhir namun tetap mempertahankan perubahannya di working directory adalah...", "git reset --soft HEAD~1", "git reset --hard HEAD~1", "git revert HEAD", "git clean -fd", "A", 1.0),
        ],
        "Cyber Security": [
            ("Serangan siber di mana penyerang membanjiri server dengan volume lalu lintas palsu yang masif hingga server down disebut...", "Phishing", "DDoS (Distributed Denial of Service)", "SQL Injection", "Cross-Site Scripting (XSS)", "B", 1.0),
            ("Karakter atau simbol yang sering diinputkan penyerang untuk menguji celah SQL Injection pada input form adalah...", "Tanda kutip tunggal (')", "Tanda pagar (#)", "Simbol ampersand (&)", "Titik dua (:)", "A", 1.0),
            ("Metode verifikasi login yang mewajibkan pengguna memasukkan kode OTP setelah password akun disebut...", "Single Sign-On (SSO)", "Multi-Factor Authentication (MFA)", "Symmetric Cryptography", "Public Key Infrastructure", "B", 1.0),
            ("Jenis malware berbahaya yang mengenkripsi file penting korban dan meminta uang tebusan untuk kunci dekripsi adalah...", "Adware", "Ransomware", "Spyware", "Rootkit", "B", 1.0),
            ("Algoritma hash satu arah yang direkomendasikan secara luas untuk menyimpan kata sandi (password hashing) secara aman adalah...", "MD5", "SHA-1", "bcrypt", "CRC32", "C", 1.0),
        ],
    }

    for station_name, q_list in sample_questions_data.items():
        st = db.session.scalar(db.select(Station).where(Station.name == station_name))
        if not st:
            continue
        qs_a = db.session.scalar(
            db.select(QuestionSet).where(
                QuestionSet.station_id == st.id,
                QuestionSet.code == "A",
            )
        )
        if qs_a:
            existing_active = [q for q in qs_a.questions if q.is_active]
            if len(existing_active) < len(q_list):
                # Hapus soal lama yang tidak lengkap jika belum ada sesi
                for old_q in qs_a.questions:
                    db.session.delete(old_q)
                db.session.flush()
                for idx, (txt, oa, ob, oc, od, ans, wt) in enumerate(q_list, start=1):
                    db.session.add(
                        Question(
                            question_set_id=qs_a.id,
                            text=txt,
                            option_a=oa,
                            option_b=ob,
                            option_c=oc,
                            option_d=od,
                            correct_answer=ans,
                            weight=wt,
                            order_number=idx,
                            is_active=True,
                        )
                    )
            # Pastikan Set A berstatus READY agar siap digunakan
            qs_a.status = QuestionSetStatus.READY

    # Seed 25 soal Pos Networking dari .agents/Panduan Pos 3 Networking.md untuk Set A-D
    net_station = db.session.scalar(db.select(Station).where(Station.name == "Networking"))
    if net_station:
        import json
        from pathlib import Path
        bank = json.loads((Path(__file__).parent / "bank_soal_networking.json").read_text(encoding="utf-8"))
        networking_questions_data = [dict(order=q["order_number"], stage=q["stage"], type=q["question_type"], cat=q.get("category"), case=q.get("case_study"), text=q["text"], a=q.get("options", {}).get("A"), b=q.get("options", {}).get("B"), c=q.get("options", {}).get("C"), d=q.get("options", {}).get("D"), e=q.get("options", {}).get("E"), ans=q["correct_answer"], acc=q.get("accepted_answers"), weight=q["weight"], external_id=q["external_id"]) for q in bank["sets"]["A"]]
        for set_code in ("A", "B", "C", "D"):
            qs_net = db.session.scalar(
                db.select(QuestionSet).where(
                    QuestionSet.station_id == net_station.id,
                    QuestionSet.code == set_code,
                )
            )
            if qs_net is None:
                qs_net = QuestionSet(
                    station_id=net_station.id,
                    code=set_code,
                    name=f"Set {set_code}",
                    status=QuestionSetStatus.READY,
                )
                db.session.add(qs_net)
                db.session.flush()

            existing_net_q = [q for q in qs_net.questions if q.is_active]
            if not qs_net.questions and qs_net.status != QuestionSetStatus.LOCKED:
                for old_q in qs_net.questions:
                    db.session.delete(old_q)
                db.session.flush()

                for qd in networking_questions_data:
                    db.session.add(
                        Question(
                            question_set_id=qs_net.id,
                            order_number=qd["order"],
                            external_id=qd["external_id"],
                            stage=qd["stage"],
                            question_type=qd["type"],
                            category=qd["cat"],
                            case_study=qd["case"],
                            text=qd["text"],
                            option_a=qd["a"],
                            option_b=qd["b"],
                            option_c=qd["c"],
                            option_d=qd["d"],
                            option_e=qd["e"],
                            correct_answer=qd["ans"],
                            accepted_answers=qd["acc"],
                            weight=qd["weight"],
                            is_active=True,
                        )
                    )
            if qs_net.status != QuestionSetStatus.LOCKED:
                qs_net.status = QuestionSetStatus.READY

    # Seed sample DRAFT Hardware packages jika belum ada
    hw_station = db.session.scalar(db.select(Station).where(Station.name == "Hardware"))
    if hw_station:
        existing_pkg = db.session.scalar(
            db.select(ChallengePackage).where(ChallengePackage.station_id == hw_station.id)
        )
        if not existing_pkg:
            sample_packages = [
                {
                    "code": "Paket 01",
                    "title": "Paket 01: Workstation AI & Deep Learning Entry-Level",
                    "case_study": "Sebuah lab kecerdasan buatan membutuhkan rancangan PC workstation entry-level untuk pelatihan model NLP dan visi komputer. Sistem harus memiliki VRAM yang memadai, pendinginan stabil, dan efisiensi daya yang baik dalam batasan anggaran.",
                    "instructions": "1. Buka BuildCores melalui tautan yang disediakan di tab baru.\n2. Rancang PC sesuai batasan budget dan target performa CPU/GPU.\n3. Salin tautan build BuildCores, masukkan rincian spesifikasi komponen pada formulir Mythic, dan unggah tangkapan layar build.",
                    "constraints": {
                        "budget_max": 25000000,
                        "currency": "IDR",
                        "region": "ID",
                        "min_cpu_score": 18000,
                        "min_gpu_score": 14000,
                        "min_ram_gb": 32,
                        "min_storage_gb": 1000,
                        "min_psu_watt": 650,
                        "required_components": ["GPU Dedicated", "SSD NVMe M.2", "Air/AIO Cooler"],
                        "forbidden_components": ["Integrated Graphics Only", "HDD as Primary Boot"],
                        "allow_used_parts": False,
                        "allow_custom_price": False,
                        "allow_discounts": False,
                        "notes": "Contoh paket draft untuk evaluasi dan simulasi panitia. Nilai target performa bukan acuan resmi."
                    },
                    "scoring_config": {
                        "weight_compatibility": 20.0,
                        "weight_budget": 15.0,
                        "weight_cpu": 15.0,
                        "weight_gpu": 20.0,
                        "weight_completeness": 10.0,
                        "weight_efficiency": 15.0,
                        "weight_time_bonus": 5.0,
                        "violation_penalty": 10.0
                    },
                },
                {
                    "code": "Paket 02",
                    "title": "Paket 02: Sistem Server Virtualisasi Mini & Proxmox",
                    "case_study": "Sebuah startup IT memerlukan rancangan rig server mini berukuran ringkas untuk menjalankan cluster Proxmox VE dengan 10 container microservices. Memerlukan core CPU tinggi dan RAM berlimpah.",
                    "instructions": "1. Buka BuildCores melalui tautan yang disediakan.\n2. Konfigurasikan spesifikasi komponen server dengan fokus kapasitas core dan memori tinggi.\n3. Masukkan data build dan tangkapan layar ke Mythic sebelum batas waktu.",
                    "constraints": {
                        "budget_max": 20000000,
                        "currency": "IDR",
                        "region": "ID",
                        "min_cpu_score": 20000,
                        "min_gpu_score": 0,
                        "min_ram_gb": 64,
                        "min_storage_gb": 2000,
                        "min_psu_watt": 550,
                        "required_components": ["Multi-core CPU", "High RAM", "SSD NVMe"],
                        "forbidden_components": ["High-end Gaming GPU", "Single Channel RAM"],
                        "allow_used_parts": False,
                        "allow_custom_price": False,
                        "allow_discounts": False,
                        "notes": "Contoh paket draft untuk evaluasi dan simulasi panitia."
                    },
                    "scoring_config": {
                        "weight_compatibility": 20.0,
                        "weight_budget": 20.0,
                        "weight_cpu": 25.0,
                        "weight_gpu": 0.0,
                        "weight_completeness": 15.0,
                        "weight_efficiency": 15.0,
                        "weight_time_bonus": 5.0,
                        "violation_penalty": 10.0
                    },
                }
            ]

            for p_data in sample_packages:
                pkg = ChallengePackage(
                    station_id=hw_station.id,
                    package_code=p_data["code"],
                    title=p_data["title"],
                    description=p_data["case_study"],
                    instructions=p_data["instructions"],
                    challenge_type=ChallengeType.HARDWARE_BUILD_CHALLENGE.value,
                    external_tool_url="https://www.buildcores.com/builds",
                    rules_config=p_data["constraints"],
                    scoring_config=p_data["scoring_config"],
                    duration_minutes=30,
                    status=PackageStatus.DRAFT,  # DRAFT sesuai instruksi: jangan diaktifkan otomatis
                )
                db.session.add(pkg)

    db.session.commit()
    print("Seed selesai.")
    print(f"Admin development: {username}")
    if "DEV_ADMIN_PASSWORD" not in os.environ:
        print("Password default: admin123 (ubah melalui DEV_ADMIN_PASSWORD sebelum seed produksi)")


if __name__ == "__main__":
    with app.app_context():
        seed_database()
