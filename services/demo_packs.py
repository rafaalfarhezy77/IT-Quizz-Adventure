"""Versioned original practice packs and synthetic hardware catalogue."""
from services.demo_questions import load_pack as software_pack

REGISTRY = {
    "software": {"name": "Software Engineering", "method": "rotation", "duration": 240},
    "cyber": {"name": "Cyber Security", "method": "quiz", "duration": 240},
    "networking": {"name": "Networking", "method": "networking", "duration": 300},
    "hardware": {"name": "Hardware", "method": "hardware", "duration": 300},
}


def question(number, text, options, key, explanation, weight=10, stage=1, kind="multiple_choice", accepted=None):
    return dict(id=number, text=text, options=dict(zip("ABCDE", options)), correct_answer=key,
                explanation=explanation, weight=weight, stage=stage, kind=kind, accepted=accepted or [])


def load_pack(slug="software"):
    if slug not in REGISTRY:
        raise ValueError("Pos demo tidak tersedia.")
    meta = REGISTRY[slug]
    if slug == "software":
        pack = software_pack()
    elif slug == "cyber":
        items = [
            ("Email meminta kata sandi melalui tautan mendesak. Apa langkah yang tepat?", ["Klik segera", "Verifikasi melalui kanal resmi", "Balas dengan kata sandi", "Teruskan ke semua orang"], "B", "Verifikasi permintaan melalui kanal resmi tanpa membuka tautan mencurigakan."),
            ("Apa manfaat MFA?", ["Menambah lapisan verifikasi identitas", "Membagikan kata sandi", "Menghilangkan semua risiko", "Mematikan pencatatan"], "A", "Faktor tambahan membantu melindungi akun ketika satu faktor bocor."),
            ("Kata sandi mana yang sebaiknya dipakai?", ["Tanggal lahir", "Sama di semua situs", "Frasa panjang unik yang disimpan dalam pengelola kata sandi", "Nama sekolah"], "C", "Kata sandi panjang dan unik mengurangi dampak kebocoran satu akun."),
            ("Hak akses siswa pada katalog sebaiknya bagaimana?", ["Semua menjadi admin", "Bisa menghapus database", "Tidak perlu verifikasi", "Hanya izin yang diperlukan untuk tugasnya"], "D", "Prinsip hak minimum membatasi perubahan yang dapat dilakukan tiap pengguna."),
            ("Bagaimana melindungi data pribadi ketika membagikan laporan latihan?", ["Hapus atau samarkan identitas yang tidak diperlukan", "Unggah semua identitas", "Sertakan kata sandi", "Kirim ke publik tanpa pemeriksaan"], "A", "Minimalkan informasi pribadi sesuai tujuan laporan."),
            ("Apa tindakan ketika menemukan akun yang diduga disalahgunakan?", ["Abaikan", "Laporkan melalui kanal resmi dan ikuti prosedur pengamanan", "Bagikan akses akun", "Hapus semua bukti"], "B", "Pelaporan dan pengamanan melalui prosedur resmi membantu penanganan insiden."),
        ]
        pack = {"version": "cyber-v1", "members": 1, "case": None,
                "questions": [question(i, *item) for i, item in enumerate(items, 1)]}
    elif slug == "networking":
        qs = [
            question(1, "Perangkat apa yang menghubungkan komputer dalam satu LAN?", ["Printer", "Speaker", "Switch", "Kamera", "Monitor"], "C", "Switch menghubungkan perangkat dalam jaringan lokal."),
            question(2, "Layanan apa yang menerjemahkan nama domain menjadi alamat IP?", ["DNS", "FTP", "NTP", "SMTP", "SSH"], "A", "DNS menyediakan pemetaan nama domain dan alamat IP."),
            question(3, "Mengapa alamat IP perangkat dalam subnet perlu unik?", ["Agar warna kabel sama", "Untuk menghindari konflik alamat", "Agar layar lebih terang", "Untuk menghapus routing", "Tidak perlu unik"], "B", "Alamat yang sama pada dua perangkat dapat menimbulkan konflik."),
        ]
        for i, (text, key, explanation) in enumerate([
            ("DHCP dapat memberikan konfigurasi IP secara otomatis.", "Benar", "DHCP menyewakan alamat dan konfigurasi jaringan kepada klien."),
            ("Switch dan router selalu memiliki fungsi yang sama.", "Salah", "Router meneruskan paket antarjaringan, sedangkan switch menghubungkan perangkat LAN."),
            ("Subnet mask membantu menentukan bagian jaringan pada alamat IPv4.", "Benar", "Subnet mask membedakan bagian jaringan dan host."),
            ("Kata sandi Wi-Fi sebaiknya dibagikan tanpa pembatasan kepada publik.", "Salah", "Batasi akses jaringan kepada pengguna yang diizinkan."),
        ], 4):
            q = question(i, text, [], key, explanation, stage=2, kind="true_false")
            q["options"] = {"Benar": "Benar", "Salah": "Salah"}
            qs.append(q)
        for i, (text, key, accepted, explanation) in enumerate([
            ("Komputer ingin menerima alamat IP otomatis. Nama layanan yang diperlukan?", "DHCP", ["dynamic host configuration protocol"], "DHCP menyediakan konfigurasi IP otomatis."),
            ("Alamat IP situs diketahui tetapi nama situs tidak terurai. Layanan apa yang diperiksa?", "DNS", ["domain name system"], "DNS menerjemahkan nama domain."),
            ("Apa nama perangkat untuk menghubungkan beberapa komputer dalam satu LAN?", "switch", ["network switch"], "Switch menghubungkan perangkat LAN."),
            ("Konfigurasi IPv4 apa yang menentukan bagian jaringan dan host?", "subnet mask", ["mask", "netmask"], "Subnet mask menunjukkan batas jaringan dan host."),
            ("Agar dapat menuju jaringan lain, komputer memerlukan alamat perangkat penghubung. Nama konfigurasi ini?", "default gateway", ["gateway"], "Default gateway merupakan jalur ke jaringan lain."),
        ], 8):
            qs.append(question(i, text, [], key, explanation, 6, 3, "short_text", accepted))
        pack = {"version": "networking-v1", "members": 1, "case": None, "questions": qs,
                "stage_seconds": [90, 60, 150], "stage_names": ["Signal Check", "True or Trap", "Case Signal"]}
    else:
        catalogue = {
            "cpu": [dict(id=f"cpu-{i}", name=f"CPU Latihan {i}", price=p, score=s, watts=w, socket=socket)
                    for i, (p, s, w, socket) in enumerate([(200, 1200, 65, "A"), (300, 1800, 95, "B"), (150, 850, 50, "A")], 1)],
            "motherboard": [dict(id=f"board-{i}", name=f"Motherboard Latihan {i}", price=p, socket=socket, ram_type=ram)
                            for i, (p, socket, ram) in enumerate([(120, "A", "DDR4"), (180, "B", "DDR5"), (140, "A", "DDR5")], 1)],
            "gpu": [dict(id=f"gpu-{i}", name=f"GPU Latihan {i}", price=p, score=s, watts=w)
                    for i, (p, s, w) in enumerate([(300, 2200, 150), (500, 3500, 250), (200, 1500, 100)], 1)],
            "ram": [dict(id=f"ram-{i}", name=f"RAM Latihan {i}", price=p, capacity=c, ram_type=t)
                    for i, (p, c, t) in enumerate([(60, 16, "DDR4"), (110, 32, "DDR5"), (35, 8, "DDR4")], 1)],
            "storage": [dict(id=f"storage-{i}", name=f"Storage Latihan {i}", price=p, capacity=c)
                        for i, (p, c) in enumerate([(80, 1000), (50, 500), (120, 2000)], 1)],
            "psu": [dict(id=f"psu-{i}", name=f"PSU Latihan {i}", price=p, watts=w)
                    for i, (p, w) in enumerate([(70, 450), (100, 650), (140, 850)], 1)],
        }
        pack = {"version": "hardware-v1", "members": 1, "questions": [], "catalogue": catalogue,
                "case": {"title": "Komputer kelas multimedia", "description": "Rancang komputer untuk kelas multimedia. Budget latihan USD 1500, target CPU 1000 dan GPU 2000. Pilih enam komponen yang kompatibel dan jelaskan alasan Anda. Harga dan performa bersifat sintetis untuk latihan."},
                "rules": {"max_budget": 1500, "min_cpu_score": 1000, "min_gpu_score": 2000, "target_efficiency": 2},
                "scoring": {"weight_compatibility": 20, "weight_budget": 15, "weight_cpu_target": 15,
                            "weight_gpu_target": 20, "weight_completeness": 10, "weight_efficiency": 15, "weight_time_bonus": 5}}
    return {**pack, **meta, "slug": slug}


def public_pack(pack):
    """Remove keys, accepted variants and model solutions before rendering."""
    return {**{key: value for key, value in pack.items() if key != "questions"},
            "questions": [{key: value for key, value in q.items()
                           if key not in ("correct_answer", "explanation", "accepted")} for q in pack["questions"]]}
