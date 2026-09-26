# Pos Networking — implementasi dan cara mencoba

## Audit

Implementasi Flask/SQLAlchemy sudah menyediakan login peserta/panitia, rotasi kelompok A–D, set soal, submission unik per sesi/tim, tiga tipe soal Networking, timer server, monitor, review isian, stamp, audit log, dan publikasi hasil ke Score/leaderboard. Pos Networking memakai kerja bersama, tanpa pergantian anggota.

Kekurangan yang diperbaiki: bobot lama 1 poin; durasi tahap 1/2 terbalik; editor dan READY masih memvalidasi A–D untuk seluruh tipe; lookup jawaban ambigu antara ID Submission dan NetworkingSubmission; submit tahap tanpa pemeriksaan urutan; autosubmit GET mustahil terpenuhi; normalisasi menghapus tanda baca; bonus manual tidak mengikuti aturan global; finalisasi dapat mengubah hasil berulang; pengiriman form tidak menunggu autosave.

Tidak ada tabel baru. Model yang sudah ada cukup untuk tipe, skenario, kunci utama, varian, dan hasil tahap. Perubahan model hanya nilai durasi bawaan untuk submission baru. Perubahan Hardware yang sudah ada di workspace dipertahankan.

## Cara mencoba

1. Jalankan website memakai launcher yang ada. Instalasi baru: jalankan `venv\Scripts\python.exe seed.py`; seed mengisi set Networking kosong saja.
2. Login panitia dan pilih Networking. Pada Bank Soal → Import JSON, unduh bank Networking atau unggah `bank_soal_networking.json`. Pilih ADD untuk set kosong atau UPDATE untuk set lama. Preview memperlihatkan tahap, skenario, kunci, varian, opsi E, dan bobot.
3. UPDATE memakai external_id `net-1` sampai `net-25` per set. Khusus data seed Networking lama tanpa external_id, UPDATE mengadopsi soal bernomor sama yang belum mempunyai external_id. LOCKED atau sesi RUNNING menolak import; data/hasil lomba lama tidak diperbarui otomatis oleh seed.
4. Tandai Set A–D READY. Validasi mewajibkan nomor 1–25, tahap dan tipe sesuai nomor, bobot 3/4/6, opsi A–E untuk tahap 1, kunci Benar/Salah untuk tahap 2, serta kunci utama dan daftar varian teks untuk tahap 3.
5. Buka Lobby Networking, pilih kelompok, rotasi, dan set dengan kode kelompok yang sama. Buka lobby lalu Mulai Sesi. Set terkunci; empat tim mendapat submission dan timer sendiri.
6. Peserta mengikuti login, pilihan pos/kelompok/tim, konfirmasi, aturan, dan ruang tunggu yang sudah ada. Tiga peserta mengerjakan bersama pada satu laptop tim. Operator menyelesaikan Signal Check → True or Trap → Case Signal → menunggu verifikasi.
7. Di monitor panitia, gunakan Tambah Waktu atau Allow Reconnect sesuai mekanisme yang ada (wajib alasan dan audit). Di Verifikasi, periksa isian yang tidak cocok, terima/tolak bila perlu, lalu finalisasi sesi. Tim yang belum mengumpulkan tahap 3 tidak dapat difinalisasi dan sesi tidak ditutup selama masih ada submission Networking belum final.
8. Peserta otomatis menuju hasil: skor tiap tahap 30/40/30, ketepatan maksimal 100, bonus kecepatan terpisah, skor final, dan stamp. Hasil final masuk leaderboard yang sudah ada.

## Durasi dan penilaian

Durasi bawaan: 600/300/900 detik dan 300 detik verifikasi, total 2100 detik. Konfigurasi startup melalui `NETWORKING_STAGE_1_SECONDS`, `NETWORKING_STAGE_2_SECONDS`, dan `NETWORKING_STAGE_3_SECONDS`; panitia juga dapat menambah waktu tahap melalui kontrol yang sudah ada. Timer tahap dibatasi sisa waktu rotasi global; refresh tidak mengulang waktu. Durasi yang sudah tersimpan pada sesi/submission lama tetap berlaku.

Bonus dibekukan saat pengumpulan tahap 3: sisa waktu sesi × `TIME_BONUS_PER_SECOND`; timeout tahap 3 mendapat bonus nol. Waktu verifikasi tidak mengurangi bonus. Parameter bonus manual lama dipertahankan untuk kompatibilitas pemanggil tetapi tidak ditambahkan ke rumus. Finalisasi idempoten.

Stamp hanya berdasarkan minimal 4/5 benar pada tahap 3 setelah verifikasi, terpisah dari skor total. Jawaban utama selalu diperiksa selain accepted_answers. Normalisasi hanya casefold dan penggabungan spasi; tanda baca, tanda hubung, dan ejaan tidak dihapus atau dicocokkan fuzzy. Jawaban tidak cocok bernilai nol dan masuk review panitia, bukan otomatis diterima.

## Keputusan atas panduan

- Markdown `.agents/Panduan Pos 3 Networking.md` menjadi sumber, menggantikan bank lama berbasis DOCX. Teks dan kunci dipertahankan; anotasi `(B)/(S)` dipindahkan ke kunci agar tidak terlihat oleh peserta. Skenario mini nomor 8/9 dipisahkan dari pernyataan tanpa mengubah kalimatnya.
- Satu bank berisi 25 soal yang sama direplikasi untuk Set A–D, total 100 butir import. Panduan tidak menyediakan empat bank berbeda; panitia dapat menyunting masing-masing set sebelum dikunci.
- Durasi mengikuti instruksi pengguna 10/5/15+5 menit, bobot 3/4/6, dan empat tim per kelompok mengikuti arsitektur website.
- Panduan bertentangan tentang jawaban langsung terkunci vs boleh diubah sebelum waktu habis. Dipilih pola website: jawaban dapat diubah selama tahap aktif, terkunci saat submit/timeout. Semua soal tahap tersedia supaya tim dapat mendahulukan soal mudah. Jika wajib satu soal per layar dan kunci sekali klik, itu masih perlu keputusan pengguna.
- Referensi kode game/QuizWhizzer diganti dengan login dan lobby native website; leaderboard resmi dipublikasikan setelah verifikasi, sesuai pola yang sudah berjalan.

## Pengujian

`venv\Scripts\python.exe -m unittest verify_networking_module -q`

Menguji 26 kasus: alur HTTP empat tim sampai hasil, tabrakan ID, isolasi set, import ADD/UPDATE data lama, LOCKED, READY, 25 soal dan bobot, lima opsi, Benar/Salah, varian dan kunci utama, penolakan normalisasi longgar, stamp 4/5 dan 3/5, timer/refresh/autosubmit, tahapan terkunci, bonus global, finalisasi idempoten, editor, preview, lobby/monitor/verifikasi panitia, serta leaderboard.

`venv\Scripts\python.exe -m unittest discover -p 'verify_*.py' -q`

Dua kegagalan lama di `verify_json_import`: `test_add_mode_and_atomic_rollback` dan `test_update_mode_by_external_id`. Fixture Software Engineering tidak memenuhi persyaratan sembilan soal. Keduanya direproduksi memakai `services/question_json_import.py` dari HEAD sebelum perubahan Networking; aturan Software Engineering tidak dilonggarkan.


## File yang diubah untuk Networking

- Backend: `services/networking_service.py`, `services/question_service.py`, `services/question_json_import.py`, `routes/participant.py`, `routes/admin.py` (bagian Networking/editor/sample).
- Model dan konfigurasi: `models/__init__.py`, `config.py`, `forms/question.py`.
- Data awal: `bank_soal_networking.json`, `seed.py`.
- UI peserta: `templates/participant/networking.html`, `templates/participant/result.html`.
- UI panitia: `templates/admin/networking/verify.html`, `templates/admin/questions/form.html`, `detail.html`, `preview.html`, `import.html`, `import_preview.html`.
- Pengujian/dokumentasi: `verify_networking_module.py`, `verify_networking_client.js`, dokumen ini.

Pengujian JavaScript: `node verify_networking_client.js` lulus untuk urutan autosave per soal, flush isian terakhir sebelum submit, tombol konfirmasi, dan timer berdasarkan waktu nyata saat tab tertunda. Pemeriksaan `node --check`, kompilasi Python, dan `git diff --check` juga lulus. Pengujian HTTP bukan pemeriksaan visual browser.

Hasil regresi: 180 pengujian Python dijalankan, 178 lulus dan dua kegagalan lama Software Engineering di atas. Sebanyak 26 pengujian khusus Networking lulus.
