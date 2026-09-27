# Impor JSON Hardware

Restart server setelah pembaruan route. Tidak diperlukan migrasi database.

1. Pilih Pos Hardware, buka **Kelola Paket Hardware → Import JSON**.
2. Unduh `bank_soal_hardware.json`, lalu isi array `packages` dengan paket yang dibutuhkan. Tidak menggunakan format Set A–D atau 9 soal.
3. Pilih ADD untuk kode baru; pilih UPDATE untuk kode existing. Kode dibandingkan setelah trim tanpa membedakan kapitalisasi. UPDATE mengganti seluruh konten paket, mempertahankan kode existing dan status.
4. Unggah file maksimal 5 MB. Periksa studi kasus, petunjuk, batasan, bobot, serta error setiap paket pada pratinjau.
5. Konfirmasi sebelum 30 menit. Semua paket disimpan dalam satu transaksi; kegagalan salah satu paket membatalkan seluruh perubahan. Kondisi database dan proteksi LOCKED/WAITING/RUNNING diperiksa kembali.
6. Paket baru menjadi DRAFT. Aktifkan melalui daftar paket, kemudian petakan Kelompok A–D melalui menu Pemetaan Hardware.

Field wajib: `package_code` (maksimal 30 karakter), `title` (200), `description`, `instructions`, URL HTTP/HTTPS `external_tool_url` (500), `duration_minutes` (bilangan bulat 1–180), `rules_config`, dan `scoring_config`. Field status, mapping, station_id, dan challenge_type tidak diterima pada paket. Root memakai `station: "Hardware"` dan `packages`.

Ketentuan wajib: `max_budget` > 0 (minimal 0.01), `currency` (10 karakter), `min_cpu_score`/`min_gpu_score` >= 0, `min_ram_gb`/`min_storage_gb` >= 1. `min_psu_watt` opsional, null atau >= 0. Field opsional memakai default formulir: region United States, daftar komponen/catatan berupa string kosong, used_parts_allowed/custom_price_allowed false, discount_allowed true. Region maksimal 50 karakter. Boolean wajib true/false, angka wajib angka JSON yang finite; jangan gunakan string angka, NaN atau Infinity.

Tujuh field bobot mengikuti contoh dan wajib berjumlah 100%, menggunakan toleransi pembulatan dua desimal sistem. Nilai tiap bobot 0–100, termasuk nol yang dipertahankan. Alias internal budget_max/weight_cpu/weight_gpu dibuat otomatis; jangan cantumkan pada file JSON. Kunci duplikat dan field tidak dikenal ditolak untuk mencegah salah ketik tersimpan diam-diam.

Impor tidak mengubah pemetaan, sesi, rumus skor, atau snapshot submission lama. Hasil paket baru mengikuti alur pengerjaan BuildCores dan verifikasi panitia yang tersedia.

Jalankan pengujian terisolasi: `venv\Scripts\python.exe verify_hardware_json_import.py`.
