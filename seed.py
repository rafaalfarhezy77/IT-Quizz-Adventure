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

    # Seed 25 soal Pos Networking dari dokumen Networking_IT_Quiz.docx untuk Set A-D
    net_station = db.session.scalar(db.select(Station).where(Station.name == "Networking"))
    if net_station:
        networking_questions_data = [
            # TAHAP 1 - Pilihan Ganda (10 soal, A-E, @1 poin)
            {"order": 1, "stage": 1, "type": "multiple_choice", "cat": "Konsep Dasar Jaringan",
             "text": "Pengertian jaringan komputer yang paling tepat adalah…",
             "a": "Sekumpulan komputer otonom yang saling terhubung menggunakan protokol komunikasi untuk berbagi data, sumber daya, dan layanan",
             "b": "Kumpulan kabel listrik dalam satu gedung", "c": "Sistem operasi untuk mengelola file", "d": "Aplikasi pengolah kata", "e": "Perangkat penyimpanan data eksternal",
             "ans": "A", "weight": 1.0, "acc": None, "case": None},
            {"order": 2, "stage": 1, "type": "multiple_choice", "cat": "Jenis Jaringan Geografis",
             "text": "Jaringan yang menghubungkan HP dengan earphone/speaker lewat Bluetooth dalam jarak sangat dekat disebut…",
             "a": "PAN", "b": "LAN", "c": "MAN", "d": "WAN", "e": "VPN",
             "ans": "A", "weight": 1.0, "acc": None, "case": None},
            {"order": 3, "stage": 1, "type": "multiple_choice", "cat": "Jenis Jaringan Geografis",
             "text": "Jaringan yang mencakup satu ruangan, satu rumah, atau satu gedung sekolah disebut…",
             "a": "PAN", "b": "LAN", "c": "MAN", "d": "WAN", "e": "GAN",
             "ans": "B", "weight": 1.0, "acc": None, "case": None},
            {"order": 4, "stage": 1, "type": "multiple_choice", "cat": "Jenis Jaringan Geografis",
             "text": "Jaringan yang menghubungkan beberapa LAN dalam cakupan satu kota disebut…",
             "a": "PAN", "b": "LAN", "c": "MAN", "d": "WAN", "e": "SAN",
             "ans": "C", "weight": 1.0, "acc": None, "case": None},
            {"order": 5, "stage": 1, "type": "multiple_choice", "cat": "Jenis Jaringan Geografis",
             "text": "Jaringan yang mencakup wilayah sangat luas (antar kota/negara/benua) dan menggunakan router disebut…",
             "a": "PAN", "b": "LAN", "c": "MAN", "d": "WAN", "e": "HAN",
             "ans": "D", "weight": 1.0, "acc": None, "case": None},
            {"order": 6, "stage": 1, "type": "multiple_choice", "cat": "Media Konektivitas",
             "text": "Media kabel yang memanfaatkan cahaya untuk mengirim data dengan kecepatan sangat tinggi dan jarak jauh adalah…",
             "a": "Kabel UTP", "b": "Kabel Coaxial", "c": "Fiber Optik", "d": "Kabel Telepon", "e": "Kabel Listrik",
             "ans": "C", "weight": 1.0, "acc": None, "case": None},
            {"order": 7, "stage": 1, "type": "multiple_choice", "cat": "Perangkat Jaringan",
             "text": "Perangkat yang berfungsi menghubungkan beberapa komputer dalam satu jaringan LAN disebut…",
             "a": "Router", "b": "Switch/Hub", "c": "Modem", "d": "Firewall", "e": "NIC",
             "ans": "B", "weight": 1.0, "acc": None, "case": None},
            {"order": 8, "stage": 1, "type": "multiple_choice", "cat": "Perangkat Jaringan",
             "text": "Perangkat yang mengatur jalur (routing) pengiriman data antar jaringan yang berbeda, misalnya dari LAN ke internet, disebut…",
             "a": "Switch", "b": "Access Point", "c": "Router", "d": "NIC", "e": "Hub",
             "ans": "C", "weight": 1.0, "acc": None, "case": None},
            {"order": 9, "stage": 1, "type": "multiple_choice", "cat": "Perangkat Jaringan",
             "text": "Kartu yang dipasang pada komputer agar dapat terhubung ke jaringan disebut…",
             "a": "Firewall", "b": "NIC (Network Interface Card)", "c": "Access Point", "d": "Switch", "e": "Modem",
             "ans": "B", "weight": 1.0, "acc": None, "case": None},
            {"order": 10, "stage": 1, "type": "multiple_choice", "cat": "Topologi Jaringan",
             "text": "Topologi jaringan di mana setiap komputer terhubung langsung ke semua komputer lain, sehingga sangat andal namun mahal, disebut topologi…",
             "a": "Bus", "b": "Star", "c": "Ring", "d": "Mesh", "e": "Tree",
             "ans": "D", "weight": 1.0, "acc": None, "case": None},

            # TAHAP 2 - Benar-Salah (10 soal, @1 poin)
            {"order": 11, "stage": 2, "type": "true_false", "cat": "Konsep Dasar Jaringan",
             "text": "Internet adalah jaringan privat yang hanya bisa diakses oleh satu sekolah saja.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Salah", "weight": 1.0, "acc": None, "case": None},
            {"order": 12, "stage": 2, "type": "true_false", "cat": "Jenis Jaringan Geografis",
             "text": "LAN biasanya mencakup wilayah yang lebih kecil dibanding MAN.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Benar", "weight": 1.0, "acc": None, "case": None},
            {"order": 13, "stage": 2, "type": "true_false", "cat": "Media Konektivitas",
             "text": "Kabel UTP termasuk media jaringan nirkabel.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Salah", "weight": 1.0, "acc": None, "case": None},
            {"order": 14, "stage": 2, "type": "true_false", "cat": "Perangkat Jaringan",
             "text": "Access Point berfungsi memancarkan sinyal WiFi agar perangkat bisa terhubung secara nirkabel.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Benar", "weight": 1.0, "acc": None, "case": None},
            {"order": 15, "stage": 2, "type": "true_false", "cat": "Perangkat Jaringan",
             "text": "Firewall berfungsi mempercepat kecepatan koneksi internet.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Salah", "weight": 1.0, "acc": None, "case": None},
            {"order": 16, "stage": 2, "type": "true_false", "cat": "Topologi Jaringan",
             "text": "Pada topologi Bus, seluruh komputer terhubung ke satu kabel utama secara berurutan.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Benar", "weight": 1.0, "acc": None, "case": None},
            {"order": 17, "stage": 2, "type": "true_false", "cat": "Topologi Jaringan",
             "text": "Pada topologi Star, jika satu kabel dari komputer ke switch putus, seluruh jaringan otomatis ikut mati total.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Salah", "weight": 1.0, "acc": None, "case": None},
            {"order": 18, "stage": 2, "type": "true_false", "cat": "Topologi Jaringan",
             "case": "Sebuah lab sekolah menghubungkan 20 komputer memakai 1 switch di tengah ruangan, dan tiap komputer punya kabel sendiri langsung ke switch tersebut.",
             "text": "Topologi yang dipakai lab ini adalah topologi Ring.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Salah", "weight": 1.0, "acc": None, "case": None},
            {"order": 19, "stage": 2, "type": "true_false", "cat": "Jenis Jaringan Geografis",
             "case": "Sebuah kios kecil menghubungkan komputer kasir ke printer struk tanpa kabel dari jarak sekitar 2 meter memakai Bluetooth.",
             "text": "Jenis jaringan yang terbentuk ini disebut PAN.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Benar", "weight": 1.0, "acc": None, "case": None},
            {"order": 20, "stage": 2, "type": "true_false", "cat": "Perangkat Jaringan",
             "text": "Router hanya bisa dipakai untuk jaringan berskala LAN dan tidak berperan apa pun dalam koneksi ke internet.",
             "a": "Benar", "b": "Salah", "c": None, "d": None, "e": None,
             "ans": "Salah", "weight": 1.0, "acc": None, "case": None},

            # TAHAP 3 - Isian Singkat / Short Text (5 soal, studi kasus berbeda)
            {"order": 21, "stage": 3, "type": "short_text", "cat": "Pertanian",
             "case": "Sebuah startup smart farming memasang banyak sensor kelembapan tanah di satu petak sawah. Sensor-sensor ini saling terhubung dalam kelompok kecil berjarak kurang dari 10 meter satu sama lain sebelum datanya dikumpulkan ke satu alat pengumpul (gateway) di pinggir sawah.",
             "text": "Jenis jaringan antar-sensor yang berjarak sangat dekat ini disebut ___",
             "a": None, "b": None, "c": None, "d": None, "e": None,
             "ans": "PAN", "weight": 1.0, "acc": ["PAN", "Personal Area Network"]},
            {"order": 22, "stage": 3, "type": "short_text", "cat": "Kesehatan",
             "case": "Sebuah klinik di desa terpencil ingin melakukan konsultasi video secara langsung dengan dokter spesialis yang bertugas di rumah sakit besar di kota lain, bahkan berbeda pulau. Meski sinyal HP di desa tersebut sering naik-turun, komunikasi video tetap harus bisa tersambung lintas pulau.",
             "text": "Jenis jaringan berskala sangat luas yang dibutuhkan agar komunikasi ini bisa berjalan disebut ___",
             "a": None, "b": None, "c": None, "d": None, "e": None,
             "ans": "WAN", "weight": 1.0, "acc": ["WAN", "Wide Area Network", "internet"]},
            {"order": 23, "stage": 3, "type": "short_text", "cat": "Ketahanan Pangan",
             "case": "Sebuah gudang penyimpanan pangan nasional memasang belasan kamera CCTV. Seluruh kamera tersebut disambungkan lewat kabel ke satu alat pusat yang diletakkan di tengah ruangan kontrol, sehingga jika salah satu kabel kamera putus, kamera-kamera lain tetap merekam normal tanpa terganggu.",
             "text": "Topologi jaringan CCTV gudang ini disebut topologi ___",
             "a": None, "b": None, "c": None, "d": None, "e": None,
             "ans": "Star", "weight": 1.0, "acc": ["Star", "topologi star", "bintang", "topologi bintang"]},
            {"order": 24, "stage": 3, "type": "short_text", "cat": "Ekonomi Sirkular/Sampah",
             "case": "Aplikasi bank sampah digital di suatu kota diakses oleh ribuan warga dari berbagai kecamatan secara bersamaan lewat internet untuk mencatat transaksi tukar sampah menjadi saldo. Agar data transaksi dan saldo warga tidak bisa diretas atau diakses sembarang orang dari luar, perangkat/sistem keamanan jaringan yang wajib dipasang di server aplikasi tersebut adalah ___",
             "text": "Perangkat/sistem keamanan jaringan yang wajib dipasang di server aplikasi tersebut adalah ___",
             "a": None, "b": None, "c": None, "d": None, "e": None,
             "ans": "Firewall", "weight": 1.0, "acc": ["Firewall", "firewall jaringan"]},
            {"order": 25, "stage": 3, "type": "short_text", "cat": "Pariwisata",
             "case": "Pengelola sebuah destinasi wisata baru ingin menyediakan akses WiFi gratis ke seluruh area terbuka objek wisata yang cukup luas, tanpa harus menarik kabel LAN ke setiap sudut area.",
             "text": "Perangkat yang perlu dipasang di beberapa titik untuk memancarkan sinyal WiFi ke seluruh area terbuka tersebut disebut ___",
             "a": None, "b": None, "c": None, "d": None, "e": None,
             "ans": "Access Point", "weight": 1.0, "acc": ["Access Point", "AP", "access point WiFi", "pemancar WiFi"]},
        ]

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
            if len(existing_net_q) < len(networking_questions_data):
                for old_q in qs_net.questions:
                    db.session.delete(old_q)
                db.session.flush()

                for qd in networking_questions_data:
                    db.session.add(
                        Question(
                            question_set_id=qs_net.id,
                            order_number=qd["order"],
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
