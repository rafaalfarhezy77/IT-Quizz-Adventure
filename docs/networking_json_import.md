# Import JSON Pos Networking

Networking memiliki tiga tahap soal, bukan sembilan soal dengan giliran anggota seperti Software Engineering. Satu tim berisi tiga peserta yang menjawab bersama di satu laptop.

## Langkah panitia

1. Login dan pilih pos Networking. Buka Bank Soal → Import JSON. Admin global dapat memilih Networking pada pilihan pos; halaman akan menampilkan format khusus Networking.
2. Klik **UNDUH JSON NETWORKING LENGKAP**. Berkas `bank_soal_networking.json` berisi 25 soal asli pada setiap Set A–D (100 butir). Set-set contoh memakai soal yang sama; panitia boleh mengubah isi set sebelum LOCKED.
3. Pilih **ADD** untuk set kosong atau **UPDATE** untuk soal yang telah diisi. UPDATE mencari `external_id` dalam set yang sama; soal seed lama tanpa ID diadopsi berdasarkan nomor urut. ID yang sama di set lain tidak mengubah soal set ini.
4. Upload. Preview menampilkan ringkasan 10/10/5 soal serta 30/40/30 poin, kemudian soal dikelompokkan per tahap. Tahap 1 menampilkan A–E, Tahap 2 menampilkan pernyataan/studi kasus dan kunci Benar/Salah, Tahap 3 menampilkan skenario, isian, kunci utama, dan varian. Tidak ada distribusi giliran anggota.
5. Periksa seluruh preview lalu konfirmasi import. Bila ada satu kesalahan atau set LOCKED/RUNNING, seluruh transaksi dibatalkan.
6. Tandai set READY, buka lobby sesuai kelompok A–D, dan mulai sesi.

## Struktur

```json
{
  "pos": "Networking",
  "schema": "networking_stages_v1",
  "sets": {
    "A": {
      "stages": {
        "1": [],
        "2": [],
        "3": []
      }
    }
  }
}
```

Array di atas adalah ilustrasi struktur saja. Import nyata harus mengisi tepat 10 soal Tahap 1, 10 soal Tahap 2, dan 5 soal Tahap 3. Unduh contoh lengkap dari halaman import.

| Tahap | Tipe | Nomor global | Bobot | Kunci / opsi |
| --- | --- | --- | --- | --- |
| 1 — Signal Check | multiple_choice | 1–10 | 3 | Lima opsi A–E, satu kunci A–E |
| 2 — True or Trap | true_false | 11–20 | 4 | Benar/Salah; tidak memakai opsi A–E |
| 3 — Case Signal | short_text | 21–25 | 6 | Kunci utama dan array varian jawaban teks |

Setiap soal memakai `external_id`, `text`, dan `correct_answer`. Dalam format grouped, `stage`, `question_type`, `weight`, dan `order_number` boleh dihilangkan; struktur tahap menetapkan nilainya. Jika disertakan, nilai harus sesuai tabel. Tidak ada `member` atau giliran anggota. Soal dikerjakan bersama dan tidak memakai studi kasus tunggal per set.

Pilihan ganda memakai `options` dengan seluruh kunci A, B, C, D, E. Benar/Salah memakai kunci `Benar` atau `Salah`. `case_study` wajib pada Tahap 2 nomor 8/9 (nomor global 18/19) dan seluruh Tahap 3. Tahap 3 menerima `accepted_answers` berupa array string; jawaban utama selalu diterima, varian harus benar secara makna. Sistem hanya menyamakan huruf besar/kecil dan spasi, tidak menghapus tanda baca atau menebak ejaan.

Format lama `sets.A` berupa array 25 soal tetap diterima bila memenuhi kontrak Networking. Bank lama yang menyatukan skenario `(Tema: ...)` dengan pertanyaan Tahap 3 dipisahkan tanpa mengubah kalimat. Format Software Engineering yang memuat 9 soal, `member`, atau studi kasus per set tidak dipakai untuk Networking.

## Pengerjaan peserta

Signal Check dan True or Trap tampil satu soal per layar. Klik pilihan mengirim dan mengunci jawaban di server; setelah sukses soal berikutnya muncul. Jawaban identik dapat dikirim ulang saat koneksi terganggu, tetapi pilihan berbeda dan lompatan nomor ditolak. Jika gagal simpan, tombol diaktifkan kembali agar tim dapat mencoba lagi. Setelah semua soal terjawab, tim menyelesaikan tahap untuk lanjut.

Case Signal menampilkan satu skenario dan isian per layar. Tombol **Simpan & Kasus Berikutnya** menunggu jawaban tersimpan; tim dapat kembali ke kasus sebelumnya sebelum pengumpulan. Saat waktu habis, tahap dikumpulkan dan dikunci. Setelah tahap 3, panitia memverifikasi hasil dan stamp minimal 4/5 benar. Ketepatan maksimal 100; bonus global tetap terpisah.
