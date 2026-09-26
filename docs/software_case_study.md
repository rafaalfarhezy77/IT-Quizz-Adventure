# Studi kasus Software Engineering

Unduh contoh lengkap melalui menu **Bank Soal → Import JSON → Unduh Contoh**. File `bank_soal.json` memuat Set A–D, masing-masing dengan struktur berikut:

```json
{
  "sets": {
    "A": {
      "case_study": {
        "title": "Judul studi kasus",
        "description": "Deskripsi skenario. Gunakan \n untuk paragraf baru."
      },
      "questions": []
    }
  }
}
```

Array `questions` pada contoh struktur di atas harus diisi **tepat 9 soal**. Gunakan struktur soal pada file unduhan: nomor 1–3 untuk anggota 1, 4–6 untuk anggota 2, dan 7–9 untuk anggota 3. Opsi dan kunci tetap A–D; bobot dan rumus skor tetap berlaku.

Format lama `{"sets": {"A": [ ...soal... ]}}` masih diterima, demikian juga pemetaan langsung A–D dan alias `paket`. Satu file boleh memadukan format lama dan baru. `case_study` opsional; jika disertakan, `title` dan `description` harus berupa teks tidak kosong. Jika tidak disertakan, studi kasus yang sudah ada dipertahankan. Teks ditampilkan sebagai teks biasa, bukan HTML.

Impor studi kasus dan soal menggunakan transaksi yang sama. Kesalahan pada salah satu set membatalkan seluruh file. Set LOCKED tidak dapat diperbarui; status diperiksa kembali saat konfirmasi impor. Pratinjau admin menampilkan studi kasus baru atau yang dipertahankan beserta hasil validasi.

Peserta Software Engineering membaca pengantar setelah sesi dimulai, sebelum soal pertama. Tombol **Mulai Kerjakan Soal** mencatat pengantar telah dibaca untuk submission tersebut; refresh dan pergantian anggota tidak mengulang pengantar otomatis. Tombol **Buka Studi Kasus** tetap tersedia selama kuis. Waktu membaca termasuk dalam durasi sesi dan tidak mengubah waktu mulai. Saat waktu habis, peserta diarahkan ke hasil melalui timer dan pemeriksaan server yang sudah berlaku. Kunci jawaban tidak dikirim pada halaman peserta.

Restart server setelah pembaruan. Migrasi startup menambahkan `question_sets.case_study` dan `submissions.case_study_seen` secara idempoten, tanpa menghapus data lama. Bank soal lama tidak otomatis mendapat studi kasus; unggah format baru dalam mode UPDATE dengan external_id yang sama untuk menambahkannya.

Jalankan regresi dengan `venv\Scripts\python.exe verify_software_case_study.py`; pengujian menggunakan SQLite sementara dan tidak menyentuh database lomba.
