# IT Quest Adventure — Demo Statis

Demo empat pos mandiri untuk GitHub Pages. Folder ini hanya berisi
HTML, CSS, JavaScript, dokumentasi, dan pengujian; tidak memerlukan Flask,
database, kredensial, API, build npm, atau layanan eksternal. Alur lomba resmi
tidak diubah.

## Audit dan alur

Acuan proyek: `templates/participant/{base,quiz,case_study}.html`,
`templates/demo/page.html`, CSS peserta/demo, dan `docs/software_case_study.md`.
Tidak ditemukan AGENTS.md pada proyek atau dua direktori induk yang diperiksa.
Metode terbaru Software Engineering: studi kasus, sembilan soal A–D, tiga
giliran anggota dengan tiga soal per giliran, penguncian setelah rotasi,
serta hasil dan pembahasan. Tampilan mengikuti panel putih, border/bayangan
hitam, latar grid, warna neon hijau, navigator, dan timer proyek.

Alur: Beranda → Pilihan Pos → Aturan → Mulai Demo → Studi Kasus → Anggota 1 →
Anggota 2 → Anggota 3 → Hasil/Pembahasan → Coba Lagi.
Satu orang dapat mensimulasikan tim. Keempat kartu pos sudah aktif. Cyber
Security memakai kuis tanpa rotasi, Networking tiga tahap, dan Hardware
tantangan rakitan dengan katalog sintetis.

Materi baru `pages-software-v1` menggunakan skenario reservasi ruang belajar.
Tidak membaca atau menyalin bank soal lomba maupun soal demo Flask.
Durasi 240 detik termasuk membaca dan transisi. Benar 10 poin, salah/kosong 0;
bonus = sisa detik utuh × 1. Timeout memberikan bonus 0.

Materi baru lainnya: `pages-cyber-v1`, `pages-networking-v1`, dan
`pages-hardware-v1`, seluruhnya dibuat khusus demo statis.

| Pos | Metode dan nilai |
| --- | --- |
| Cyber Security | 6 soal A–D, 240 detik, benar 10 poin + bonus sisa detik |
| Networking | 3 soal A–E / 90 detik, 4 Benar/Salah / 60 detik, 5 isian / 150 detik; nilai 30/40/30 + bonus; batas keseluruhan 300 detik |
| Hardware | 6 komponen dan alasan, 300 detik; bobot aspek 95 dan bonus maksimal 5 |

Networking mengunci pilihan tahap 1/2 setelah tersimpan. Timeout tahap 1/2
membuka transisi; tahap 3 atau deadline keseluruhan menyelesaikan percobaan
dengan bonus nol. Timer tahap berikutnya dimulai setelah konfirmasi, sementara
deadline keseluruhan terus berjalan. Isian menerima variasi terdaftar dengan
normalisasi kapitalisasi/spasi. Minimal 4 dari 5 benar pada tahap 3 memperoleh
Stempel Latihan; penalti demo nol.

Hardware menggunakan kasus studio podcast: budget USD 1400, target CPU 1100,
GPU 1900, target efisiensi 2. Nilai kompatibilitas 20, budget 15, CPU 15,
GPU 20, kelengkapan 10, efisiensi 15; bonus proporsional sisa waktu maksimal 5.
Socket CPU/board, jenis RAM, dan daya PSU diperiksa dari katalog. Daya minimum
adalah CPU + GPU + 100 W. Kelengkapan skor mengikuti fungsi proyek (CPU, GPU,
RAM, storage, PSU); kompatibilitas mensyaratkan enam pilihan termasuk board.
Alasan maksimal 1000 karakter, disimpan tanpa nilai otomatis. Submit normal
memerlukan enam pilihan dan alasan; timeout menilai rakitan parsial. Harga dan
performa sintetis; tidak memakai BuildCores/upload/verifikasi panitia.

Aturan Hardware menyertakan panduan enam langkah BuildCores, tautan situs,
tutorial YouTube oleh MrKnow, kanal resmi BuildCores, dan panduan berbahasa
Indonesia dari darkFlash. Panduan juga
dapat dibuka dari bagian pengerjaan. Tautan terbuka di tab baru; demo tidak
memuat video/layanan eksternal otomatis. Pelajari sebelum mulai, karena timer
tetap berjalan saat membuka tutorial selama pengerjaan. Tidak ada impor rakitan
atau perubahan penilaian demo.

- [BuildCores](https://www.buildcores.com/builds)
- [Tutorial YouTube](https://www.youtube.com/watch?v=82eJ6YFSess)
- [Kanal resmi BuildCores](https://www.youtube.com/@BuildCores)
- [Panduan bahasa Indonesia](https://www.darkflash.com/id-ID/article/visualize-pc-build-in-3D-with-buildcores)

Judul tutorial: **Build Your Dream Gaming PC in Minutes Using BuildCores –
Step-by-Step Guide**, pembuat **MrKnow**. Judul dan pembuat diverifikasi melalui
metadata YouTube; panduan teks mengikuti langkah di artikel darkFlash dan
fitur BuildCores. Pelajari sebelum Mulai Demo agar waktu latihan tidak terpakai.

## Menjalankan lokal

Dari root proyek:

```powershell
.\venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory demo-pages
```

Buka `http://127.0.0.1:8080/`, lalu **Coba Demo**. Python di sini hanya server
file statis; `app.py` tidak dijalankan. Python sistem juga dapat dipakai.
Hentikan server dengan Ctrl+C.

Untuk mensimulasikan subfolder repository tanpa backend:

```powershell
.\venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1
```

Buka `http://127.0.0.1:8080/demo-pages/`. Gunakan hanya untuk pemeriksaan lokal;
hosting harus mempublikasikan folder demo-pages saja.

## GitHub Pages

`index.html` dan `.nojekyll` tersedia di root folder ini. Semua aset memakai
path relatif (`./assets/...`). Navigasi memakai hash (`#rules`, `#quiz`, dst.)
agar refresh tidak meminta route yang tidak ada pada server statis.

Pilihan hosting:

1. **Repository khusus demo:** salin isi folder ini ke root repository khusus,
   commit/push, lalu Settings → Pages → Deploy from a branch → pilih branch
   dan folder `/ (root)`.
2. **Repository proyek saat ini:** workflow sudah tersedia di
   `.github/workflows/demo-pages.yml`; ia mengunggah hanya isi `demo-pages/`
   setiap ada push perubahan demo ke branch `main`. Sesuaikan nama branch di
   workflow bila berbeda. Atur Settings → Pages → Source → **GitHub Actions**
   satu kali. Sesudah itu, Sync commit demo akan menerbitkannya otomatis.

Keduanya menghasilkan URL `https://<akun>.github.io/<repository>/`.
Folder arbitrer `demo-pages/` tidak dapat dipilih langsung pada pilihan sumber
branch Pages; gunakan workflow artifact atau repository khusus seperti di atas.
Jika sudah ada website GitHub Pages pada repository yang sama, gunakan
repository khusus supaya demo tidak menggantikan website tersebut.
Workflow menerbitkan halaman setelah commit didorong ke GitHub. Perintah Sync
IDE melakukan push commit tersebut; GitHub Actions menjalankan deployment.

## Penyimpanan dan pemulihan

- Key khusus per pos: `itquest:github-pages:<slug>:attempt:v1`, dengan slug
  `software`, `cyber`, `networking`, atau `hardware`. Key serta format progres
  Software Engineering lama tetap dipertahankan.
- Menyimpan percobaan terbaru setiap pos di browser: ID, versi, waktu mulai,
  deadline, giliran, jawaban, revisi, dan hasil. Tidak ada identitas resmi.
- Jawaban langsung tersimpan. Refresh tidak mereset timer. Timeout diproses
  saat halaman aktif kembali; waktu tetap berjalan saat tab tidak aktif.
- TTL 24 jam. JSON rusak, ukuran berlebih, nilai invalid, deadline invalid,
  dan versi pack berubah menghasilkan pesan untuk mulai baru. Hanya key demo
  dibersihkan, bukan seluruh localStorage.
- Coba Lagi memerlukan konfirmasi, mengganti percobaan lokal dengan ID baru.
  Pergantian pos atau coba lagi tidak menghapus progres pos lain.
  Browser/profil berbeda independen; tab dalam browser sama berbagi percobaan
  dan menyinkronkan perubahan melalui event storage. Gunakan satu tab pengerjaan.
- Jika storage diblokir/penuh, ada pesan dan fallback memori. Dalam kondisi
  tersebut refresh tidak dapat mempertahankan progres.
- Skor tersimpan dihitung ulang ketika dibaca. Jawaban tidak bisa diubah lewat
  UI setelah selesai atau setelah gilirannya dikunci.

Ini latihan statis: soal, kunci, waktu, dan nilai berada di browser sehingga
dapat diperiksa/diubah melalui developer tools. Pembahasan hanya ditampilkan
pada UI setelah selesai. Tidak cocok sebagai penilaian lomba atau sistem anti
kecurangan. Mengubah jam perangkat dapat memengaruhi timer.

## Pengujian

Pengujian logika tanpa browser:

```powershell
node --test demo-pages/tests/engine.test.cjs demo-pages/tests/methods.test.cjs
```

Pengujian penuh dari root proyek (Python standar + Node 22+ + Chrome/Edge):

```powershell
.\venv\Scripts\python.exe verify_demo_pages.py
```

`DEMO_TEST_BROWSER` dapat menunjuk executable Chromium lain. Runner menggunakan
server HTTP statis, menyalin **hanya demo-pages** ke direktori sementara, dan
menguji URL `/repository-name/demo-pages/`. Tidak mengakses database resmi.

Hasil: 30 pengujian logika lulus; browser desktop 1366×900 dan ponsel 390×844
lulus untuk alur lengkap, dialog, refresh/progres/deadline, penguncian hasil,
coba lagi, timeout, offline, data rusak, perubahan versi, independensi browser,
sinkronisasi dua tab, fallback storage, dan navigasi hash tidak dikenal.
Keempat pos diuji sampai hasil. Pengujian juga memeriksa progres Software
Engineering format lama, variasi isian, skor/stempel Networking, deadline
tahap, penilaian komponen Hardware, dan independensi penyimpanan antarpos.
Tidak ada error JavaScript/HTTP atau request API/backend. Seluruh request
halaman dibatasi pada aset statis di subfolder repository.
Screenshot pemeriksaan tersedia di `scratch/demo-pages-browser/` setelah uji
(tidak masuk artifact/Git); tampilan laptop dan ponsel diperiksa secara visual.

## File dan perluasan

- `index.html`, `.nojekyll`: titik masuk hosting statis.
- `assets/style.css`: gaya responsif mandiri dengan webfont lokal WOFF2 (Space Grotesk & JetBrains Mono) tanpa dependensi CDN eksternal.
- `assets/fonts/`: font lokal WOFF2 mandiri agar tampilan Neo-Brutalism konsisten 100% offline.
- `assets/questions.js`: studi kasus, soal latihan, versi, durasi, tarif bonus.
- `assets/engine.js`: validasi progres, penyimpanan, aturan jawaban, penilaian.
- `assets/app.js`: tampilan, hash navigation, timer, dialog, autosave.
- `assets/packs.js`: registry materi baru dan katalog sintetis tiga pos.
- `assets/methods.js`: validasi state dan adapter penilaian/timer tiga pos.
- `assets/modules.js`: pengerjaan dan hasil sesuai metode tiap pos.
- `tests/engine.test.cjs`: pengujian logika.
- `tests/methods.test.cjs`: pengujian ketiga metode tambahan.
- `github-pages.yml.example`: template deployment opsional.

Ketika soal/aturan berubah, naikkan `pack.version` agar progres lama tidak
dinilai memakai kunci baru. Untuk pos berikutnya, tambahkan pack serta adapter
metode yang sesuai, gunakan namespace penyimpanan per pos, dan aktifkan kartu
setelah alur dan pengujian lengkap tersedia.
