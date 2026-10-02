# Mode Demo dan Masa Demo

Panduan peserta tersedia dalam [PDF](panduan_demo.pdf) dan [HTML](panduan_demo.html), dengan 19 screenshot aplikasi aktual. Gambar tertanam dalam HTML sehingga dokumen dapat dibagikan tanpa folder gambar tambahan.

## Audit dan penggunaan ulang

Tidak ditemukan AGENTS.md pada proyek atau induknya. Audit mengikuti README, petunjuk `.agents`, route, model, service, template, dan pengujian. Proyek memakai Flask application factory, Blueprint, Flask-WTF CSRF, SQLAlchemy, dan SQLite. Demo tidak membuat Team, Group, CompetitionSession, Submission, Answer, atau Score resmi.

Software Engineering memakai studi kasus dan rotasi tiga anggota; Cyber Security memakai kuis pilihan ganda; Networking resmi memakai tiga tahap dan fasilitator; Hardware resmi memakai BuildCores, upload, dan peninjauan panitia. Demo menyediakan simulasi mandiri sesuai metode setiap pos.

Digunakan kembali: base peserta, template kuis, navigasi, modal, pembagian soal, serta fungsi matematika penilaian. Risiko perubahan ada pada template/JS bersama, autentikasi, dan permulaan sesi resmi; suite regresi menguji bagian tersebut. Tidak ditemukan fitur feedback yang dapat dihubungkan.

## Mengaktifkan dan mencoba

Untuk menyediakan demo dengan akses lomba tetap terbuka (mode Normal):

```powershell
$env:DEMO_ENABLED = "1"
.\venv\Scripts\python.exe app.py
```

Buka beranda → **Coba Demo** → pilihan pos → aturan → **Mulai Demo** → pengerjaan → hasil. Semua empat pos tersedia tanpa login, tim, atau panitia.

Untuk membatasi akses umum selama masa latihan:

1. Login sebagai admin aktif melalui **Login Admin**.
2. Buka **Pengaturan Akses Website** dari sidebar panel.
3. Pilih **Masa Demo**, simpan, lalu konfirmasikan.
4. Untuk membuka lomba kembali, pilih **Normal** dan simpan.

Perubahan tersimpan di database resmi tanpa restart. Masa Demo mengaktifkan demo meskipun `DEMO_ENABLED=0`. Mengaktifkannya ditolak jika ada sesi resmi RUNNING. Admin aktif tetap dapat membuka panel dan alur resmi dengan persyaratan konteks peserta yang berlaku. Akses pengunjung umum ke peserta, API, leaderboard, dan berkas resmi ditolak di backend, termasuk cookie peserta lama. Identitas peserta dibersihkan ketika akses resmi ditolak; setelah Normal dipulihkan peserta memasukkan kode kembali. Riwayat menyimpan admin, waktu, mode sebelumnya/sesudahnya. Statistik demo terpisah dari hasil resmi.

`DEMO_ENABLED=0` menutup demo hanya dalam mode Normal. Environment dibaca dari proses; `.env` tidak dimuat otomatis oleh `python app.py`. Untuk HTTPS gunakan `SESSION_COOKIE_SECURE=1`, secret key yang sama pada semua worker, dan debug mati. Cookie HttpOnly, SameSite=Lax, dan CSRF tetap berlaku. Login/logout admin mempertahankan pemilik demo pada browser yang sama.

## Metode latihan dan nilai

| Pos / versi | Durasi | Metode |
| --- | --- | --- |
| Software Engineering / software-v1 | 240 detik | Studi kasus, 9 soal A–D, 3 giliran; benar 10 poin + bonus sisa detik |
| Cyber Security / cyber-v1 | 240 detik | 6 soal A–D, tanpa rotasi; benar 10 poin + bonus sisa detik |
| Networking / networking-v1 | 300 detik | 3 soal A–E (90 detik), 4 Benar/Salah (60), 5 isian (150); bobot 30/40/30 + bonus |
| Hardware / hardware-v1 | 300 detik | Pilih 6 komponen katalog sintetis dan alasan; skor aspek maksimal 95 + bonus maksimal 5 |

Networking mengunci pilihan tahap 1/2 saat tersimpan. Transisi memulai tahap berikutnya, sementara deadline keseluruhan tetap berjalan. Isian tahap 3 menerima variasi terdaftar; kapitalisasi/spasi dinormalisasi. Minimal 4 dari 5 benar memperoleh **Stempel Latihan**. Penalti demo nol; service fasilitator resmi tidak dipanggil.

Hardware mengevaluasi socket, jenis RAM, daya PSU, budget, performa, kelengkapan, dan efisiensi melalui fungsi skor bersama. Harga/performa berasal dari server. Alasan disimpan tanpa nilai otomatis. Contoh rakitan tersedia setelah selesai. Katalog sintetis bukan rekomendasi harga/produk nyata. Tidak memerlukan BuildCores, upload, atau layanan berbayar.

Materi dibuat khusus latihan, bukan salinan bank soal lomba. Sumbernya `services/demo_questions.py` dan `services/demo_packs.py`. Setiap percobaan menyimpan snapshot versi, soal, aturan, dan tarif bonus; perubahan materi tidak mengubah percobaan berjalan. Kunci dan pembahasan tidak dikirim selama pengerjaan.

## Data, timer, dan batas

Database khusus default `instance/demo.db`, diatur melalui `DEMO_DATABASE_PATH`, tanpa FK ke tim/sesi/hasil resmi. ID berawalan `demo_`; setiap operasi memeriksa ID dan token pemilik dari cookie bertanda tangan. Endpoint resmi menolak penanda/identitas demo. Coba Lagi membuat ID baru.

Deadline/waktu mulai disimpan server; refresh mempertahankan timer dan progres. Autosave memakai revisi agar tab tertinggal tidak menimpa perubahan; konflik meminta refresh. Transaksi `BEGIN IMMEDIATE` menserialisasi perubahan antar-worker. Submit berulang mengembalikan satu hasil; jawaban selesai terkunci. Percobaan software-v1 lama tetap dapat dilanjutkan.

Deadline keseluruhan memfinalisasi pada request berikutnya (polling, refresh, submit), tanpa background worker, dengan bonus nol. Deadline Networking tahap 1/2 membuka transisi; tahap 3 mengakhiri percobaan. Saat offline hanya jawaban tersimpan yang dipastikan bertahan, timer tetap berjalan. Sesi dan hasil kedaluwarsa 24 jam sejak dibuat.

Batas default: 12 start/pemilik/jam, 60 start/IP/jam, 5.000 percobaan tersimpan, body request 8 KiB. IP disimpan sebagai HMAC. Forwarded headers tidak dipercaya otomatis; proxy hosting perlu dikonfigurasi sesuai topologi. Pengguna satu NAT dapat berbagi batas IP.

Semua worker harus menggunakan secret key dan file demo yang sama pada disk persisten dengan locking SQLite. Beberapa host atau disk ephemeral memerlukan adapter penyimpanan bersama. Pembersihan otomatis dilakukan saat start; hosting dapat menjadwalkan:

```powershell
.\venv\Scripts\python.exe -m flask --app app cleanup-demo
```

## File utama

- Backend baru: `routes/demo.py`, `services/{demo_service,demo_packs,demo_questions,access_service,score_math}.py`.
- Akses diubah: `models/__init__.py`, `quiz_app/__init__.py`, `utils/auth.py`, `routes/admin.py`, `services/{session_service,networking_service}.py`.
- Tampilan: `templates/demo/`, `templates/admin/access_settings.html`, base admin/peserta, landing, quiz peserta, `static/css/demo.css`, `static/js/{quiz,demo_timer,demo_module}.js`.
- Konfigurasi/skor: `config.py`, `.env.example`, `services/scoring_service.py`.
- Pengujian/panduan: `verify_demo*.py`, `verify_demo_browser.js`, `docs/build_demo_guide.py`, `docs/demo_guide_sections.py`, README, dan dokumen panduan.

## Pengujian dan screenshot

```powershell
.\venv\Scripts\python.exe -m unittest verify_demo verify_demo_modes
.\venv\Scripts\python.exe -m unittest verify_step5 verify_step6 verify_step7 verify_step8 verify_global_leaderboard verify_software_case_study verify_networking_module verify_hardware_module
.\venv\Scripts\python.exe verify_demo_browser.py
.\venv\Scripts\python.exe docs/build_demo_guide.py
```

Suite demo memakai database sementara: independensi browser, isolasi tabel resmi, ownership, timer/progres refresh, submit berulang/bersamaan, revisi, timeout/TTL, migrasi store lama, CSRF, batas request/start, materi tidak tersedia, empat pos, mode akses, audit, admin tidak aktif, dan sesi RUNNING. Suite resmi menguji peserta, panitia, leaderboard, serta semua metode lomba.

Browser menggunakan Chrome/Edge headless, Node 22+, viewport 1366×900 dan 390×844. Meliputi seluruh pos sampai hasil, rotasi/tahap, dialog, refresh, koneksi terputus/pulih, serta admin mengaktifkan Masa Demo. Screenshot di `scratch/demo-browser/` (diabaikan Git); `DEMO_TEST_BROWSER` dapat menunjuk Chromium lain. Google Fonts opsional diblokir dalam uji agar memakai fallback lokal. Builder menggabungkan 19 screenshot; cetak HTML menggunakan Chromium atau tombol Cetak untuk memperbarui PDF.

Hasil verifikasi implementasi: **188 pengujian lulus**, terdiri dari 24 pengujian demo, 161 regresi metode/hasil resmi, serta 3 pemeriksaan login/admin (`verify_step2`, `verify_admin_ux`). Alur browser empat pos lulus pada kedua viewport. Panduan diverifikasi berisi 19 PNG tertanam dan PDF 21 halaman.

## Menambah demo berikutnya

Daftarkan pack berversi pada `REGISTRY` di `services/demo_packs.py`. Pakai metode yang ada jika sesuai; metode baru membutuhkan adapter pengerjaan/penilaian. Gunakan fungsi skor murni, bukan service yang menulis hasil resmi. Pertahankan snapshot, ownership, revisi, deadline, dan kunci hanya setelah selesai. Tambahkan pengujian isolasi/alur browser sebelum mengaktifkan kartu. Perbarui panduan/screenshot ketika metode berubah.

Tidak ada deployment yang dilakukan oleh implementasi ini.
