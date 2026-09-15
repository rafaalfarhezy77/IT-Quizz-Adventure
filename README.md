# IT Quest Adventure — Mythic 3.0

> **Platform Kompetisi Cerdas Cermat IT Berbasis Stasiun Pos (Station-Based Quiz Platform)**  
> Dirancang khusus untuk perlombaan luring berbasis jaringan lokal (*Offline LAN*) dengan performa tinggi, desain Neo-Brutalist yang modern, serta sistem anti-kecurangan yang andal.

---

## 📋 Daftar Isi

- [Tentang Proyek](#-tentang-proyek)
- [Arsitektur & Teknologi](#-arsitektur--teknologi)
- [Fitur Utama](#-fitur-utama)
- [Struktur Direktori](#-struktur-direktori)
- [Keamanan & Variabel Lingkungan](#-keamanan--variabel-lingkungan)
- [Panduan Instalasi & Menjalankan](#-panduan-instalasi--menjalankan)
  - [Cara Cepat (1-Click Launcher Windows)](#1-cara-cepat-1-click-launcher-windows)
  - [Cara Manual (Terminal / PowerShell)](#2-cara-manual-terminal--powershell)
- [Panduan Deployment Jaringan Lokal (LAN)](#-panduan-deployment-jaringan-lokal-lan)
- [Alur Kerja Kompetisi](#-alur-kerja-kompetisi)
- [Checklist Keamanan Menjelang Lomba](#-checklist-keamanan-menjelang-lomba)

---

## 🚀 Tentang Proyek

**IT Quest Adventure** adalah sistem manajemen perlombaan cerdas cermat teknologi informasi interaktif untuk **Mythic 3.0**. Peserta berkompetisi dalam format penjelajahan pos/stasiun (*station quiz*) dengan berbagai bidang ilmu (misal: *Software Engineering*, *Cyber Security*, *Networking*, *Hardware*).

Sistem ini memfasilitasi rotasi kelompok, verifikasi tim, sinkronisasi ruang tunggu sesi, pengerjaan kuis berbasis batas waktu dengan penalti/bonus waktu, mode pos khusus (*Member Rotation*), hingga kalkulasi otomatis papan peringkat (*leaderboard*) secara transparan dan akurat.

---

## 🛠️ Arsitektur & Teknologi

- **Backend**: Python 3.10+ & [Flask](https://flask.palletsprojects.com/) (menggunakan pola *Application Factory* dan modular *Blueprints*).
- **Database & ORM**: SQLite dengan [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/).
  - Mode **WAL (*Write-Ahead Logging*)** aktif untuk konkurensi baca/tulis yang optimal.
  - Penegakan integritas data relasional via `PRAGMA foreign_keys = ON` pada setiap koneksi.
- **Form & Proteksi**: [Flask-WTF](https://flask-wtf.readthedocs.io/) dengan perlindungan **CSRF (*Cross-Site Request Forgery*)** penuh pada seluruh interaksi form.
- **Frontend**: Antarmuka responsif tanpa dependensi CDN eksternal (100% aset lokal untuk keandalan jaringan *offline* penuh).
  - **Styling**: Vanilla CSS kustom bertema **Neo-Brutalism** (kontras tinggi, tipografi teknis, border tegas).
  - **Scripting**: Vanilla JavaScript untuk *real-time countdown timer*, polling ruang tunggu, dan auto-submit.

---

## ✨ Fitur Utama

### 1. 🛡️ Portal Peserta (Participant Portal)
- **Gerbang Kode Akses**: Verifikasi peserta melalui kode akses resmi pos lomba sebelum memilih kelompok.
- **Seleksi Stasiun & Kelompok**: Peserta memilih stasiun pos dan kelompok (A–D), lalu mengonfirmasi identitas tim dari daftar terdaftar.
- **Konfirmasi Aturan Pos**: Ringkasan aturan spesifik stasiun (durasi pengerjaan, bobot nilai, dan mekanisme khusus).
- **Ruang Tunggu Terpusat (Waiting Room)**: Sinkronisasi status sesi secara otomatis dengan server panitia sebelum kuis dimulai.
- **Antarmuka Ujian Interaktif**:
  - Timer hitung mundur (*countdown*) sinkron dengan server.
  - Auto-submit otomatis jika waktu pengerjaan habis.
  - Mode Khusus: **Member Rotation** (soal dikerjakan bergantian oleh anggota tim secara berurutan).
- **Halaman Hasil & Leaderboard**: Rekapitulasi perolehan poin per stasiun dan status submission.

### 2. 🎛️ Panel Kontrol Panitia (Admin Control Console)
- **Autentikasi Aman**: Login berbasis session terlindungi hash password kuat dan proteksi CSRF.
- **Dashboard Metrik**: Ringkasan jumlah pos aktif, kelompok, tim terdaftar, ketersediaan bank soal, dan sesi berjalan.
- **Manajemen Bank Soal**:
  - CRUD (*Create, Read, Update, Delete*) soal dan set soal (Set A, B, C, D).
  - Status siklus soal: `DRAFT`, `READY`, dan `LOCKED`.
  - Import soal massal dari file JSON (`bank_soal.json`) atau file CSV.
  - Pemisahan data: Kunci jawaban (`correct_answer`) disimpan strictly di sisi server dan tidak pernah dikirim ke browser peserta.
- **Manajemen Tim & Peserta**: Registrasi tim baru, pemetaan kelompok, dan import CSV master tim.
- **Kontrol Sesi Real-Time**:
  - Membuka, memantau, dan menyelesaikan sesi kuis per pos.
  - Pemantauan status live tim yang sedang terhubung dan mengerjakan.
- **Sistem Penilaian & Leaderboard**:
  - Perhitungan skor baku (*raw score*).
  - Kalkulasi *time bonus* per detik sisa waktu pengerjaan.
  - Penentuan peringkat otomatis dengan penanganan nilai seri (*tie-breaking*).
  - Export rekap hasil perlombaan.

---

## 📂 Struktur Direktori

```text
IT Quizz Adventure/
├── app.py                      # Entry point server Flask
├── config.py                   # Konfigurasi sistem & pemuatan environment variable
├── requirements.txt            # Daftar dependensi Python
├── seed.py                     # Script inisialisasi master data database
├── Jalankan Website.bat        # Launcher 1-klik untuk Windows
├── launcher.ps1                # Skrip helper launcher (proteksi single-instance mutex)
│
├── quiz_app/                   # Application factory
│   └── __init__.py             # Inisialisasi Flask app, SQLite PRAGMA, ekstensi & error handlers
│
├── models/                     # Skema database (SQLAlchemy)
│   └── __init__.py             # Model Admin, Station, Group, Team, QuestionSet, Question, Session, dll.
│
├── routes/                     # Modul routing (Flask Blueprints)
│   ├── admin.py                # Endpoint panel admin, manajemen kuis, sesi, & tim
│   ├── participant.py          # Endpoint alur peserta (akses, pos, kuis, leaderboard)
│   └── api.py                  # API monitoring sesi, status waktu, dan sinkronisasi
│
├── services/                   # Business logic layer
│   ├── scoring_service.py      # Logika perhitungan nilai akhir & bonus waktu
│   ├── leaderboard_service.py  # Logika peringkat dan rekapitulasi poin
│   ├── session_service.py      # Logika manajemen siklus hidup sesi kuis
│   ├── question_service.py     # Logika seleksi & penyajian soal aman
│   ├── question_json_import.py # Parser & validator import soal JSON
│   └── csv_import.py           # Parser import CSV peserta & soal
│
├── forms/                      # Form validation & CSRF (Flask-WTF)
├── utils/                      # Helper autentikasi & validasi session
├── templates/                  # Template HTML Jinja2
│   ├── admin/                  # Tampilan dashboard & manajemen panitia
│   ├── participant/            # Tampilan alur kompetisi peserta
│   ├── errors/                 # Halaman error responsif (403, 404, 500)
│   └── landing.html            # Halaman awal pemilihan portal
│
├── static/                     # Aset statis lokal (CSS & JS)
│   ├── css/                    # admin.css & participant.css (Neo-Brutalist design)
│   └── js/                     # quiz.js, session_timer.js, waiting.js
│
└── instance/                   # Lokasi database SQLite (competition.db)
```

---

## 🔐 Keamanan & Variabel Lingkungan

Untuk menjaga integritas dan kerahasiaan kompetisi, **jangan pernah mencantumkan kredensial asli, password panitia, kode akses peserta, atau secret key pada repositori publik**.

Gunakan environment variables atau file `.env` sebelum menjalankan aplikasi.

### Daftar Variabel Lingkungan

| Variabel | Deskripsi | Rekomendasi Nilai |
| :--- | :--- | :--- |
| `SECRET_KEY` | Kunci enkripsi sesi Flask & CSRF token | String acak yang panjang dan unik (min. 32 karakter) |
| `DEV_ADMIN_USERNAME` | Username awal untuk akun administrator saat *seeding* | Tentukan username panitia yang aman |
| `DEV_ADMIN_PASSWORD` | Password akun administrator saat *seeding* | Password kuat dengan kombinasi huruf, angka, dan simbol |
| `PARTICIPANT_ACCESS_CODE` | Kode rahasia yang wajib dimasukkan peserta di gerbang awal | Kode rahasia yang hanya diumumkan panitia saat sesi dimulai |
| `FLASK_DEBUG` | Mode debug aplikasi | Set `0` untuk hari perlombaan / produksi; `1` hanya untuk dev |
| `SESSION_COOKIE_SECURE` | Penggunaan cookie HTTPS | Set `0` jika memakai HTTP LAN lokal; `1` jika memakai HTTPS |
| `TIME_BONUS_PER_SECOND` | Nilai tambahan poin bonus per detik sisa waktu | Default: `1.0` (dapat disesuaikan aturan juri) |
| `MEMBER_ROTATION_COUNT` | Jumlah rotasi anggota tim pada pos khusus rotasi | Default: `3` |

> ⚠️ **PENTING**:
> Ganti seluruh nilai default sebelum hari perlombaan berlangsung. Pastikan peserta tidak memiliki akses fisik maupun jaringan ke file konfigurasi atau database `instance/competition.db`.

---

## 💻 Panduan Instalasi & Menjalankan

### Persyaratan Sistem
- Windows 10/11 (atau Linux/macOS)
- Python versi **3.10** atau lebih baru
- Hak akses port `5000` pada firewall lokal

---

### 1. Cara Cepat (1-Click Launcher Windows)

Jika sudah menyiapkan dependensi di folder `venv`, Anda dapat langsung menjalankan:

```text
Klik 2x pada file: "Jalankan Website.bat"
```

*Skrip ini akan mengunci single-instance menggunakan Mutex (mencegah double-click yang memicu duplikasi server), memulai server pada background, dan otomatis membuka browser ke alamat aplikasi.*

---

### 2. Cara Manual (Terminal / PowerShell)

#### Langkah 1: Buat Virtual Environment
Buka PowerShell atau Command Prompt pada direktori proyek:

```powershell
python -m venv venv
```

Aktifkan virtual environment:
- **PowerShell**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  *(Jika muncul error Execution Policy, jalankan: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*
- **Command Prompt (CMD)**:
  ```cmd
  venv\Scripts\activate.bat
  ```

#### Langkah 2: Install Dependensi
```powershell
pip install -r requirements.txt
```

#### Langkah 3: Konfigurasi Kredensial & Kunci Rahasia
Atur variabel lingkungan sebelum melakukan seeding database:

- **PowerShell**:
  ```powershell
  $env:SECRET_KEY = "masukkan-string-acak-rahasia-anda"
  $env:DEV_ADMIN_USERNAME = "masukkan-username-admin"
  $env:DEV_ADMIN_PASSWORD = "masukkan-password-admin-yang-kuat"
  $env:PARTICIPANT_ACCESS_CODE = "masukkan-kode-akses-peserta"
  $env:FLASK_DEBUG = "0"
  ```

- **Command Prompt (CMD)**:
  ```cmd
  set SECRET_KEY=masukkan-string-acak-rahasia-anda
  set DEV_ADMIN_USERNAME=masukkan-username-admin
  set DEV_ADMIN_PASSWORD=masukkan-password-admin-yang-kuat
  set PARTICIPANT_ACCESS_CODE=masukkan-kode-akses-peserta
  set FLASK_DEBUG=0
  ```

#### Langkah 4: Inisialisasi Database (Seed Data)
Jalankan skrip seed untuk membuat skema database, akun admin, stasiun pos awal, dan set soal:

```powershell
python seed.py
```

#### Langkah 5: Jalankan Server
```powershell
python app.py
```

Server akan aktif dan mendengar koneksi pada `http://0.0.0.0:5000` (dapat diakses dari localhost maupun perangkat lain dalam jaringan lokal yang sama).

---

## 🌐 Panduan Deployment Jaringan Lokal (LAN)

Agar peserta di laptop atau tablet lain dapat membuka aplikasi:

1. **Hubungkan Perangkat ke Jaringan yang Sama**:
   - Pastikan laptop server panitia dan perangkat peserta terhubung ke router Wi-Fi atau switch LAN yang sama.
2. **Cek Alamat IPv4 Server**:
   - Buka terminal server, ketik `ipconfig` (Windows) atau `ifconfig` / `ip a` (Linux).
   - Catat alamat IPv4 lokal server, misalnya: `192.168.1.50`.
3. **Konfigurasi Windows Firewall**:
   - Izinkan port `5000` (atau aplikasi Python) pada profil jaringan **Private Network**.
   - Jangan membuka jaringan ke Publik untuk menghindari akses luar yang tidak diinginkan.
4. **Akses Peserta**:
   - Peserta membuka browser dan memasukkan URL:
     ```text
     http://192.168.1.50:5000/
     ```
   - Peserta memilih peran **PESERTA LOMBA** dan memasukkan **Kode Akses Resmi** yang diberikan panitia di lokasi pos.

---

## 🔄 Alur Kerja Kompetisi

```text
[Peserta Membuka Web]
         │
         ▼
[Input Kode Akses Resmi] ── (Verifikasi Kode Rahasia Panitia)
         │
         ▼
[Pilih Stasiun Pos & Kelompok (A–D)]
         │
         ▼
[Pilih Nama Tim & Konfirmasi Aturan]
         │
         ▼
[Ruang Tunggu (Waiting Room)] ◄─── (Sinkronisasi status dengan Server)
         │
         ├──────────────────── (Panitia memulai sesi di panel admin)
         ▼
[Pengerjaan Kuis Interaktif]
         ├── Timer Hitung Mundur Server
         ├── Mode Normal / Member Rotation
         └── Submit Jawaban (Manual / Auto-submit saat waktu habis)
         │
         ▼
[Kalkulasi Skor Otomatis] ── (Skor Benar + Time Bonus)
         │
         ▼
[Halaman Hasil & Leaderboard Pos]
```

---

## 🛡️ Checklist Keamanan Menjelang Lomba

Sebelum perlombaan resmi dimulai, pastikan panitia telah memeriksa hal-hal berikut:

- [ ] **Ganti Password Default**: Pastikan akun admin tidak menggunakan kata sandi bawaan/prediktabel.
- [ ] **Atur SECRET_KEY Unik**: Gunakan string acak panjang untuk mencegah pemalsuan session cookie.
- [ ] **Tentukan Kode Akses Baru**: Ganti `PARTICIPANT_ACCESS_CODE` dengan kode khusus yang baru disosialisasikan saat pembukaan pos.
- [ ] **Matikan Debug Mode**: Pastikan `FLASK_DEBUG=0` agar stack trace error tidak membocorkan struktur internal server ke peserta.
- [ ] **Validasi Bank Soal**: Kunci jawaban soal telah diverifikasi kebenarannya melalui panel admin sebelum set soal diubah ke status `READY`.
- [ ] **Kunci Set Soal Selesai**: Ubah status set soal menjadi `LOCKED` setelah sesi selesai agar tidak dapat diubah kembali.
- [ ] **Backup Database**: Cadangkan file `instance/competition.db` secara berkala sebelum dan sesudah tiap babak perlombaan.

---

## 📄 Lisensi & Hak Cipta

Dikembangkan untuk kebutuhan internal perlombaan **Mythic 3.0 — IT Quest Adventure**. Seluruh hak cipta modul sistem dan soal kuis berada pada panitia penyelenggara.
