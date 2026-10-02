/* Original static-demo practice pack; independent from every competition bank. */
(function (root) {
  'use strict';
  const pack = {
    version: 'pages-software-v1', duration: 240, members: 3, bonusPerSecond: 1,
    title: 'Software Engineering',
    caseTitle: 'Reservasi ruang belajar komunitas',
    caseText: 'Komunitas Ruang Bersama membutuhkan aplikasi reservasi ruang belajar. Pengunjung memilih ruang dan slot waktu, membuat reservasi, lalu dapat membatalkannya. Pengelola mengatur ruang dan jadwal. Satu ruang tidak boleh memiliki dua reservasi aktif pada slot yang sama. Slot yang dibatalkan harus tersedia kembali. Tim terdiri dari analis, pengembang, dan penguji. Dalam demo ini, satu orang dapat memainkan ketiga peran.',
    questions: [
      {id: 1, text: 'Kebutuhan manakah yang menjelaskan perilaku utama aplikasi?', options: ['Pengunjung dapat membatalkan reservasinya', 'Logo menggunakan tiga warna', 'Judul ditulis dengan huruf besar', 'Semua kartu memiliki bayangan'], key: 'A', explanation: 'Kebutuhan fungsional menjelaskan tindakan yang dapat dilakukan pengguna, seperti membatalkan reservasi.'},
      {id: 2, text: 'Informasi apa yang perlu digali analis dari pengelola sebelum merancang jadwal?', options: ['Merek mouse pengelola', 'Jam operasional dan aturan lama pemakaian ruang', 'Warna favorit pengembang', 'Jumlah gambar pada halaman awal'], key: 'B', explanation: 'Jam operasional dan durasi pemakaian menentukan aturan slot yang benar untuk proses reservasi.'},
      {id: 3, text: 'Kriteria penerimaan mana yang paling jelas untuk fitur pembatalan?', options: ['Pembatalan terasa cepat', 'Halaman pembatalan terlihat keren', 'Setelah reservasi dibatalkan, slot dapat dipesan lagi', 'Semua pengunjung pasti menyukai aplikasi'], key: 'C', explanation: 'Kondisi setelah pembatalan dapat diamati dan diuji: slot kembali tersedia untuk reservasi baru.'},
      {id: 4, text: 'Bagaimana mencegah dua reservasi aktif pada ruang dan slot yang sama?', options: ['Menyembunyikan tombol setelah klik saja', 'Meminta pengguna tidak klik bersamaan', 'Mengganti warna slot di browser saja', 'Menerapkan validasi server dan batas unik pada penyimpanan'], key: 'D', explanation: 'Aturan harus dijaga pada server dan penyimpanan karena dua permintaan dapat tiba bersamaan dari browser berbeda.'},
      {id: 5, text: 'Status apa yang tepat ketika pengguna yang sama mengirim pembatalan dua kali?', options: ['Reservasi tetap dibatalkan tanpa perubahan tambahan', 'Slot lain ikut dibatalkan', 'Reservasi kembali aktif', 'Seluruh jadwal dihapus'], key: 'A', explanation: 'Pembatalan yang idempoten menjaga hasil tetap sama meskipun permintaan yang sama dikirim ulang.'},
      {id: 6, text: 'Mengapa aturan konflik jadwal sebaiknya dipisahkan dari komponen tampilan?', options: ['Agar validasi hanya berjalan saat layar terbuka', 'Agar aturan dapat diuji dan digunakan oleh beberapa antarmuka', 'Agar data jadwal disimpan di warna tombol', 'Agar perubahan aturan tidak perlu diperiksa'], key: 'B', explanation: 'Pemisahan logika bisnis memungkinkan pengujian aturan tanpa merender halaman dan mengurangi duplikasi.'},
      {id: 7, text: 'Kasus pengujian mana yang paling langsung memeriksa konflik reservasi?', options: ['Mengubah gambar sampul', 'Membuka halaman bantuan', 'Dua pengunjung memesan ruang dan slot yang sama bersamaan', 'Mengganti jenis huruf footer'], key: 'C', explanation: 'Permintaan bersamaan pada pasangan ruang-slot yang sama menguji apakah hanya satu reservasi diterima.'},
      {id: 8, text: 'Setelah memperbaiki pembatalan, pengujian regresi apa yang relevan?', options: ['Memeriksa posisi logo saja', 'Menghapus pengujian reservasi', 'Mengubah seluruh data uji menjadi kosong', 'Memeriksa pembatalan, pemesanan ulang, dan reservasi biasa'], key: 'D', explanation: 'Regresi memeriksa alur yang terkait agar perbaikan pembatalan tidak merusak pemesanan baru maupun pemesanan ulang.'},
      {id: 9, text: 'Bukti apa yang paling membantu saat melaporkan slot masih tertutup setelah dibatalkan?', options: ['Langkah reproduksi, ruang/slot terkait, hasil aktual dan harapan', 'Hanya kalimat aplikasi rusak', 'Hanya warna latar halaman', 'Hanya nama pembuat laporan'], key: 'A', explanation: 'Langkah, konteks ruang-slot, dan perbandingan hasil membantu pengembang mereproduksi serta memverifikasi masalah.'}
    ]
  };
  root.DemoPack = pack;
  if (typeof module !== 'undefined') module.exports = pack;
}(globalThis));
