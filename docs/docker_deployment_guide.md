# 🚀 Panduan Deployment Docker di Server Kampus
## IT Quest Adventure — Mythic 3.0

Panduan ini disusun untuk mempermudah administrator atau tim teknis dalam mendeploy aplikasi **IT Quest Adventure** ke server kampus berbasis **Docker & Docker Compose**.

---

## 🏗️ 1. Arsitektur Deployment

Aplikasi berjalan di dalam container Docker yang telah dioptimalkan untuk lingkungan produksi:
* **Base Image**: `python:3.11-slim` (ringan dan aman).
* **WSGI Production Server**: [Gunicorn](https://gunicorn.org/) (4 workers, 2 threads per worker) untuk menangani request kuis secara simultan dan stabil.
* **Database Persisten**: SQLite dengan mode **WAL (*Write-Ahead Logging*)** yang disimpan di direktori volume host `./instance:/app/instance`. Data peserta, sesi, dan jawaban tidak akan hilang saat container di-restart atau di-rebuild.
* **Auto-Seed & Migration**: Script entrypoint otomatis menjalankan inisialisasi awal (`seed.py`) dan migrasi skema saat container pertama kali dijalankan.
* **Automated Healthcheck**: Memantau ketersediaan aplikasi dan koneksi database di `/api/health`.

---

## 📋 2. Prasyarat di Server Kampus

Pastikan server kampus telah terpasang:
1. **Docker Engine** (versi 20.10+ disarankan)
2. **Docker Compose** (versi v2 atau `docker-compose`)
3. Akses terminal / SSH ke server kampus.

Verifikasi instalasi di server:
```bash
docker --version
docker compose version
```

---

## 🛠️ 3. Langkah-Langkah Setup ke Server

### Langkah 1: Salin Kode Proyek ke Server Kampus
Anda dapat menggunakan `git clone` atau mentransfer folder proyek via `scp` / SFTP:

```bash
# Contoh clone repository (jika di-host di GitHub/GitLab kampus)
git clone https://github.com/rafaalfarhezy77/IT-Quizz-Adventure.git /opt/it-quizz-adventure
cd /opt/it-quizz-adventure
```

---

### Langkah 2: Buat dan Sesuaikan File Konfigurasi `.env`
Salin template `.env.example` menjadi `.env`:

```bash
cp .env.example .env
```

Buka file `.env` menggunakan teks editor (misalnya `nano .env`):
```bash
nano .env
```

**Variabel penting yang wajib diperiksa & disesuaikan:**

```ini
# 1. Kunci rahasia enkripsi sesi (Wajib unik & acak)
# Tips membuat kunci acak: jalankan perintah: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=b7c89f2a4e1d6c8b9a0e2f3d4c5b6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f

# 2. Mode Debug (Wajib 0 untuk server kampus/produksi)
FLASK_DEBUG=0

# 3. Keamanan Cookie Sesi
# Set ke 1 jika server kampus menggunakan HTTPS/SSL
# Set ke 0 jika server hanya diakses via HTTP / IP LAN
SESSION_COOKIE_SECURE=1

# 4. Kredensial Administrator Awal (Panel Panitia)
DEV_ADMIN_USERNAME=admin
DEV_ADMIN_PASSWORD=admin123

# 5. Kode Akses Peserta (Diberikan kepada peserta saat kuis dimulai)
PARTICIPANT_ACCESS_CODE=MYTHIC2026

# 6. Proteksi Safe Exam Browser (SEB)
# 0 = Fleksibel (peserta bisa membuka via Chrome/Edge maupun SEB)
# 1 = Wajib SEB (browser biasa langsung diblokir dan diarahkan ke SEB)
SEB_ENFORCED=0
SEB_QUIT_PASSWORD=itquest2026

# 7. Port Server Host (Opsional, default: 5000)
HOST_PORT=5000
```

Simpan file dengan menekan `Ctrl + O` lalu `Enter`, dan keluar dengan `Ctrl + X`.

---

### Langkah 3: Build dan Jalankan Container
Jalankan perintah berikut di folder proyek:

```bash
docker compose up -d --build
```

Docker akan:
1. Mengunduh base image Python 3.11.
2. Memasang seluruh dependencies (`Flask`, `Gunicorn`, `SQLAlchemy`, dll).
3. Memeriksa file database SQLite di `./instance/competition.db`.
4. Jika database belum ada, sistem akan otomatis melakukan **seeding awal** (membuat akun admin, kelompok A–D, pos lomba, dan bank soal default).
5. Menjalankan Gunicorn production server di port `5000`.

---

### Langkah 4: Verifikasi Status Container
Periksa apakah container telah berjalan dengan baik:

```bash
docker compose ps
```

Output yang diharapkan:
```text
NAME                   IMAGE                    COMMAND                  SERVICE    STATUS
it-quizz-adventure     it-quizz-adventure-app   "/app/entrypoint.sh"     quiz-app   Up (healthy)
```

Untuk melihat log aplikasi secara langsung:
```bash
docker compose logs -f
```

Uji akses endpoint healthcheck:
```bash
curl http://localhost:5000/api/health
# Output yang diharapkan: {"database":"ok","status":"ok"}
```

Aplikasi sekarang sudah aktif dan dapat diakses di browser pada:
* Peserta: `http://<IP_SERVER_KAMPUS>:5000/`
* Panitia: `http://<IP_SERVER_KAMPUS>:5000/admin/login`

---

## 🔒 4. Setup Domain Kampus & SSL (Nginx Reverse Proxy)

Untuk performa optimal dan penggunaan protokol HTTPS (sangat disarankan saat menggunakan Safe Exam Browser), pasang **Nginx** di server host sebagai *Reverse Proxy*.

File template siap pakai telah disediakan di [`docs/nginx_reverse_proxy_sample.conf`](file:///e:/KULIAH%20SEMESTER%203/Mythic%203.0/IT%20Quizz%20Adventure/docs/nginx_reverse_proxy_sample.conf).

### Langkah Cepat Setup Nginx di Ubuntu/Debian:
```bash
# 1. Pasang Nginx dan Certbot
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx

# 2. Salin template konfigurasi
sudo cp docs/nginx_reverse_proxy_sample.conf /etc/nginx/sites-available/quiz.kampus.ac.id

# 3. Sesuaikan server_name dengan domain kampus
sudo nano /etc/nginx/sites-available/quiz.kampus.ac.id

# 4. Aktifkan konfigurasi
sudo ln -s /etc/nginx/sites-available/quiz.kampus.ac.id /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 5. Pasang Sertifikat SSL Gratis (Let's Encrypt)
sudo certbot --nginx -d quiz.kampus.ac.id
```

Setelah HTTPS aktif, pastikan di `.env`:
```ini
SESSION_COOKIE_SECURE=1
```
Lalu jalankan `docker compose up -d` untuk memuat ulang variabel.

---

## 🛡️ 5. Cara Penggunaan Safe Exam Browser (SEB) di Server Kampus

Karena aplikasi telah dilengkapi fitur **Dynamic SEB Config Generator**:
1. Saat server kampus berjalan di domain resmi (misal `https://quiz.kampus.ac.id`), buka:
   * **`https://quiz.kampus.ac.id/seb/download`**: Otomatis menghasilkan file `.seb` dengan *Start URL* yang mengarah ke `https://quiz.kampus.ac.id/participant/access`.
2. Panitia cukup mengunduh file tersebut dari browser dan mendistribusikannya ke peserta, atau membagikan tautan 1-klik:
   * **`sebs://quiz.kampus.ac.id/seb/config.seb`**
3. Jika pada hari-H panitia ingin memastikan tidak ada peserta yang memakai browser biasa:
   * Masuk ke **Dashboard Admin** (`/admin/dashboard`).
   * Klik tombol **"Aktifkan Wajib SEB"** pada kartu Safe Exam Browser, atau ubah `SEB_ENFORCED=1` di file `.env`.

---

## 🧰 6. Perintah Pemeliharaan & Troubleshooting

### Melihat Log Real-time:
```bash
docker compose logs -f quiz-app
```

### Menghentikan Aplikasi Sementara:
```bash
docker compose stop
```

### Menjalankan Kembali:
```bash
docker compose start
```

### Melakukan Backup Database Kuis:
Semua database tersimpan di direktori host `./instance`. Untuk backup, cukup salin file:
```bash
# Backup sebelum lomba dimulai
cp instance/competition.db instance/competition_backup_$(date +%Y%m%d_%H%M%S).db
```

### Mereset Database ke Kondisi Awal:
Jika ingin membersihkan seluruh sesi uji coba dan kembali ke soal/tim bawaan:
```bash
docker compose exec quiz-app python seed.py
```

### Menjalankan Perintah CLI / Shell di dalam Container:
```bash
# Membuka terminal bash di dalam container
docker compose exec quiz-app bash

# Menjalankan pembersihan sesi latihan demo yang kedaluwarsa
docker compose exec quiz-app flask cleanup-demo
```

### Mengubah Konfigurasi `.env`:
Cukup edit file `.env`, lalu jalankan:
```bash
docker compose up -d
```
Container akan di-restart otomatis dengan konfigurasi baru tanpa menghapus data database.
