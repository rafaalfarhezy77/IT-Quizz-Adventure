"""Build a self-contained participant guide using actual demo screenshots."""
import base64
import html
from pathlib import Path

root = Path(__file__).resolve().parent.parent
shots = root / "scratch" / "demo-browser"
sections = [
    ("1. Buka website dan pilih Coba Demo", "desktop-landing.png",
     "Tombol Coba Demo pada halaman awal website.",
     "<p>Buka alamat website yang dibagikan panitia melalui browser. Pada halaman awal, klik <strong>Coba Demo</strong>. Jika mencoba aplikasi di komputer server lokal, gunakan <code>http://localhost:5000/</code>.</p><p>Demo tidak memerlukan login, kode akses, kelompok, atau tim resmi. Jika tombol belum terlihat, hubungi pengelola website untuk mengaktifkan Mode Demo.</p>"),
    ("2. Pilih pos Software Engineering", "desktop-select.png",
     "Pilihan empat pos demo beserta tautan panduan.",
     "<p>Klik <strong>Coba Demo</strong> pada pos pilihan Anda. Software Engineering, Cyber Security, Networking, dan Hardware tersedia. Langkah 3–10 mencontohkan Software Engineering; metode pos lain dijelaskan berikutnya.</p><p>Gunakan <strong>Lanjutkan Percobaan</strong> untuk sesi aktif pada browser ini. Memulai lagi membuat percobaan baru setelah konfirmasi; percobaan lain tetap tersimpan.</p>"),
    ("3. Baca aturan dan mulai percobaan", "desktop-rules.png",
     "Halaman aturan dan tombol Mulai Demo.",
     "<p>Latihan terdiri dari <strong>9 soal</strong> pilihan ganda A–D, dibagi menjadi <strong>3 giliran anggota</strong> dengan 3 soal per giliran. Anda boleh mengerjakan ketiga giliran sendirian untuk mensimulasikan satu tim.</p><p>Durasi latihan <strong>4 menit</strong>. Klik <strong>Mulai Demo</strong> ketika siap. Timer mulai berjalan saat tombol ini ditekan, termasuk waktu membaca studi kasus dan pergantian anggota.</p><p>Jawaban benar bernilai 10 poin; salah atau kosong bernilai 0. Bonus mengikuti tarif yang tertulis pada aturan: pada konfigurasi contoh, sisa detik × 1 poin. Bonus waktu menjadi 0 jika waktu habis.</p>"),
    ("4. Baca studi kasus", "desktop-case.png",
     "Pengantar studi kasus sebelum mengerjakan soal.",
     "<p>Baca skenario <strong>Aplikasi peminjaman buku kelas</strong>, lalu klik <strong>Mulai Kerjakan Soal</strong>. Informasi skenario membantu Anda menjawab soal.</p><p>Timer terus berjalan selama membaca. Saat mengerjakan, gunakan <strong>Buka Studi Kasus</strong> untuk membaca kembali, lalu pilih <strong>Kembali ke Soal</strong>. Membuka ulang studi kasus tidak menambah waktu.</p>"),
    ("5. Jawab soal dan periksa penyimpanan", "desktop-quiz-actions.png",
     "Pilihan jawaban, navigasi soal, status penyimpanan, dan tombol menyelesaikan bagian anggota.",
     "<p>Klik salah satu pilihan <strong>A, B, C, atau D</strong>. Gunakan nomor pada <strong>Navigator Soal</strong> atau tombol <strong>Soal Sebelumnya / Soal Selanjutnya</strong> untuk berpindah di dalam giliran yang sedang aktif.</p><p>Jawaban disimpan otomatis. Periksa indikator <strong>Tersimpan</strong> setelah memilih jawaban. Anda masih boleh mengganti jawaban selama giliran tersebut belum diselesaikan dan waktu belum habis.</p><p>Refresh mempertahankan timer dan jawaban yang sudah berhasil tersimpan. Angka soal pada navigator dihitung untuk giliran yang sedang aktif.</p>"),
    ("6. Selesaikan giliran dan ganti anggota", "desktop-transition-1.png",
     "Halaman pergantian menuju Anggota 2; alur yang sama digunakan menuju Anggota 3.",
     "<p>Setelah memeriksa tiga soal, klik <strong>Selesaikan Bagian Anggota 1</strong>, lalu konfirmasikan dengan <strong>Kunci Bagian &amp; Lanjutkan</strong>. Pada halaman pergantian, klik <strong>Lanjutkan Anggota 2</strong>.</p><p>Ulangi proses untuk Anggota 2 hingga memasuki Anggota 3. Jika mencoba sendirian, cukup lanjutkan sebagai anggota berikutnya pada browser yang sama. Jawaban giliran sebelumnya terkunci dan tidak dapat diubah. Timer tidak berhenti saat berganti anggota.</p>"),
    ("7. Kirim jawaban akhir", "desktop-submit-confirm.png",
     "Dialog konfirmasi submit; soal yang masih kosong mendapat 0 poin.",
     "<p>Pada Anggota 3, pilih <strong>Kirim Semua Jawaban Tim</strong>. Klik <strong>Kembali Periksa Soal</strong> untuk memperbaiki bagian aktif, atau <strong>Ya, Saya Yakin Kirim</strong> untuk selesai.</p><p>Ringkasan submit menghitung <strong>seluruh 9 soal</strong>, termasuk giliran sebelumnya. Setelah submit, seluruh jawaban terkunci. Saat waktu habis, jawaban tersimpan dinilai dengan bonus 0.</p>"),
    ("8. Lihat skor dan status penyelesaian", "desktop-result.png",
     "Ringkasan hasil: status, jumlah soal terjawab, skor jawaban, bonus waktu, dan skor akhir.",
     "<p>Halaman hasil menampilkan status <strong>Selesai dikirim</strong> atau <strong>Waktu habis</strong>, jumlah soal terjawab, skor jawaban, bonus waktu, dan skor akhir.</p><p><strong>Skor akhir = skor jawaban + bonus waktu.</strong> Contoh: 6 jawaban benar dan sisa 30 detik pada tarif 1 poin/detik menghasilkan 60 + 30 = 90 poin. Angka pada screenshot hanya contoh percobaan; nilai Anda dapat berbeda.</p><p>Nilai demo tidak dihitung dalam lomba dan tidak masuk leaderboard, rekap, atau ekspor resmi.</p>"),
    ("9. Pelajari jawaban dan pembahasan", "desktop-result-review.png",
     "Rincian jawaban pengguna, jawaban benar, dan pembahasan setelah latihan selesai.",
     "<p>Gulir halaman hasil untuk memeriksa setiap soal. Bandingkan <strong>Jawaban Anda</strong> dengan <strong>Jawaban benar</strong>, kemudian baca pembahasannya. Soal yang belum dijawab ditandai <strong>Belum dijawab</strong>.</p><p>Kunci jawaban dan pembahasan baru tersedia setelah percobaan selesai.</p>"),
    ("10. Coba lagi atau kembali ke pilihan pos", "desktop-result-actions.png",
     "Tombol Coba Lagi dan Kembali ke Pilihan Pos di bagian bawah halaman hasil.",
     "<p>Klik <strong>Coba Lagi</strong> di bagian bawah hasil, lalu setujui konfirmasi untuk membuat percobaan baru. Anda akan kembali membaca studi kasus dengan timer baru.</p><p>Percobaan baru memiliki identitas dan jawaban sendiri; hasil percobaan lama tidak diubah. Klik <strong>Kembali ke Pilihan Pos</strong> jika ingin meninggalkan halaman hasil.</p>"),
    ("Menggunakan demo di ponsel", "mobile-quiz-actions.png",
     "Tampilan pengerjaan pada ponsel; gulir untuk melihat pilihan jawaban dan tombol tindakan.",
     "<p>Alur pada ponsel sama seperti laptop. Gunakan browser yang sama sepanjang percobaan, gulir halaman untuk melihat semua pilihan dan tombol, lalu periksa indikator penyimpanan sebelum menyelesaikan giliran.</p><p>Dua browser atau perangkat yang berbeda menjalankan sesi masing-masing. Membuka demo pada perangkat lain tidak melanjutkan jawaban di perangkat pertama.</p>"),
]

from demo_guide_sections import extra_sections
sections.extend(extra_sections)
chunks = []
for index, (title, filename, caption, paragraphs) in enumerate(sections, 1):
    raw = (shots / filename).read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n"), filename
    data = base64.b64encode(raw).decode()
    image_class = ' class="mobile-shot"' if filename.startswith("mobile") else ""
    chunks.append(f'<section id="langkah-{index}"><h2>{html.escape(title)}</h2>{paragraphs}'
                  f'<figure><img{image_class} src="data:image/png;base64,{data}" alt="{html.escape(caption)}">'
                  f'<figcaption>Gambar {index}. {html.escape(caption)}</figcaption></figure></section>')

toc = "".join(f'<li><a href="#langkah-{i}">{html.escape(s[0])}</a></li>' for i, s in enumerate(sections, 1))
document = '''<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panduan Peserta Mode Demo · IT Quest Adventure</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f5ef;color:#151515;font:16px/1.65 Arial,sans-serif}
main{max-width:1000px;margin:auto;padding:32px 24px}header,section,aside{background:white;border:2px solid #151515;padding:28px;margin-bottom:28px;box-shadow:5px 5px 0 #151515}
.badge{display:inline-block;background:#b5ff30;border:2px solid;padding:3px 12px;font-weight:bold}h1{font-size:clamp(28px,5vw,42px);line-height:1.15}h2{font-size:25px;line-height:1.3}p{margin:14px 0}a{color:#234500}button{cursor:pointer;background:#b5ff30;border:2px solid;padding:12px 18px;font-weight:bold;font-size:16px}code{overflow-wrap:anywhere}
figure{margin:22px 0 0}img{display:block;width:100%;height:auto;border:1px solid #ccc}.mobile-shot{max-width:320px;margin:auto}figcaption{font-size:14px;color:#444;margin-top:8px}.meta{color:#555;font-size:14px}li{margin:5px 0}table{border-collapse:collapse;width:100%;font-size:15px}td,th{text-align:left;border:1px solid #ccc;padding:12px;vertical-align:top}th{background:#efffd7}nav ol{columns:2;column-gap:28px}nav li{break-inside:avoid}
@media(max-width:600px){main{padding:16px}header,section,aside{padding:18px}nav ol{columns:1}table,tbody,tr,td,th{display:block}th{display:none}td:first-child{font-weight:bold;background:#efffd7}}
@media print{@page{size:A4;margin:14mm}body{background:white;font-size:10.5pt;line-height:1.5}main{max-width:none;padding:0}header,section,aside{border:0;box-shadow:none;padding:0;margin:0}section,aside{break-before:page}h1{font-size:28pt}h2{font-size:18pt;margin-top:0}figure{break-inside:avoid;margin-top:14px}img{max-height:160mm;object-fit:contain;object-position:left top}.mobile-shot{max-height:140mm;width:auto;max-width:100%}button,nav{display:none}figcaption,.meta{font-size:9pt}a{color:inherit;text-decoration:none}*{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
</style></head><body><main>
<header><span class="badge">MODE DEMO · PANDUAN PESERTA</span>
<h1>Cara Mencoba IT Quest Adventure</h1><p><strong>Empat Pos Latihan · Mythic 3.0</strong></p>
<p>Panduan ini membantu Anda mencoba konsep kuis sebelum lomba. Latihan memakai soal khusus, bisa dilakukan oleh satu orang, dan tidak memerlukan panitia untuk memulai sesi.</p>
<p><strong>Siapkan:</strong> laptop atau ponsel, browser, koneksi ke website, dan empat hingga lima menit per percobaan. Pengelola dapat mengaktifkan Masa Demo melalui panel admin.</p>
<p><strong>Alur:</strong> Beranda → Pilihan Pos → Aturan → Pengerjaan sesuai metode pos → Hasil.</p>
<p class="meta">Versi panduan 2 · 1 Oktober 2026 · Screenshot berasal dari aplikasi lokal dengan materi latihan berversi. Teks dan nilai adalah contoh.</p>
<button type="button" onclick="window.print()">Cetak / Simpan sebagai PDF</button>
<nav aria-label="Daftar isi"><h2>Langkah pengerjaan</h2><ol>__TOC__</ol><a href="#kendala">Jika mengalami kendala</a></nav></header>
__SECTIONS__
<aside id="kendala"><h2>Jika mengalami kendala</h2>
<table><thead><tr><th>Kondisi</th><th>Yang perlu dilakukan</th></tr></thead><tbody>
<tr><td>Tombol Coba Demo tidak terlihat</td><td>Pastikan membuka beranda website yang benar. Minta pengelola mengaktifkan Mode Demo. Konfigurasi pengelola dijelaskan dalam docs/demo.md.</td></tr>
<tr><td>Indikator Menyimpan atau Koneksi terputus</td><td>Periksa koneksi dan tunggu hingga status kembali Tersimpan. Timer tetap berjalan. Jangan refresh sebelum jawaban tersimpan; jawaban yang belum terkirim dapat hilang. Submit saat koneksi pulih sebelum deadline akan membawa pilihan yang masih tampil pada bagian aktif.</td></tr>
<tr><td>Waktu habis saat membaca atau menjawab</td><td>Deadline keseluruhan menyelesaikan percobaan dengan bonus 0. Pada Networking, deadline tahap 1 atau 2 membuka transisi; mulai tahap berikutnya jika masih ada waktu keseluruhan. Saat offline, sambungkan kembali untuk melihat status. Jawaban baru setelah deadline tidak diterima.</td></tr>
<tr><td>Percobaan berubah di tab lain</td><td>Muat ulang untuk mengambil progres terbaru. Gunakan satu tab pengerjaan agar jawaban tidak saling bertabrakan.</td></tr>
<tr><td>Sesi kedaluwarsa atau tidak ditemukan</td><td>Sesi dan hasil tersedia selama 24 jam sejak percobaan dibuat. Gunakan Mulai Ulang atau kembali ke pilihan pos lalu mulai demo baru. Sesi dari browser lain tidak dapat dibuka sebagai sesi Anda.</td></tr>
<tr><td>Batas percobaan tercapai atau demo sedang penuh</td><td>Tunggu sesuai pesan yang ditampilkan. Untuk batas percobaan per jam, coba kembali dalam satu jam.</td></tr>
<tr><td>Soal latihan belum tersedia</td><td>Kembali ke pilihan pos dan coba lagi nanti. Jika berulang, laporkan kepada pengelola website.</td></tr>
</tbody></table><p><strong>Pengingat:</strong> nilai demo hanya untuk latihan. Jawaban terkunci setelah giliran diselesaikan atau percobaan selesai. Coba Lagi membuat percobaan baru.</p></aside>
</main></body></html>'''
document = document.replace("__TOC__", toc).replace("__SECTIONS__", "\n".join(chunks))
target = root / "docs" / "panduan_demo.html"
target.write_text(document, encoding="utf-8")
print(f"Created {target.name}: {len(sections)} embedded screenshots, {target.stat().st_size:,} bytes")
