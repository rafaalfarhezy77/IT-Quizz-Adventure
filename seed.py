import os

from werkzeug.security import generate_password_hash

from app import app
from models import Admin, Group, QuestionSet, QuestionSetStatus, Station, StationMode, db


def seed_database():
    db.create_all()

    for code in ("A", "B", "C", "D"):
        if not db.session.scalar(db.select(Group).where(Group.code == code)):
            db.session.add(Group(code=code))

    stations = {
        "Software Engineering": StationMode.MEMBER_ROTATION,
        "Cyber Security": StationMode.NORMAL,
        "Hardware": StationMode.BELUM_DIKETAHUI,
        "Networking": StationMode.BELUM_DIKETAHUI,
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

    db.session.commit()
    print("Seed selesai.")
    print(f"Admin development: {username}")
    if "DEV_ADMIN_PASSWORD" not in os.environ:
        print("Password default: admin123 (ubah melalui DEV_ADMIN_PASSWORD sebelum seed produksi)")


if __name__ == "__main__":
    with app.app_context():
        seed_database()
