"""Original practice material. Never read the competition question bank."""
from types import SimpleNamespace

VERSION = "software-v1"
STATIONS = ("Software Engineering", "Networking", "Cyber Security", "Hardware")
CASE = {
    "title": "Aplikasi peminjaman buku kelas",
    "description": "Sebuah kelas membuat aplikasi peminjaman buku. Siswa dapat melihat buku yang tersedia, meminjam satu buku, dan mengembalikannya. Petugas mengelola katalog. Setiap peminjaman harus tercatat dan stok tidak boleh negatif. Tim terdiri dari analis, pengembang, dan penguji. Satu orang boleh memainkan ketiga peran dalam latihan ini.",
}

# Nine original questions; three questions per simulated member.
_ITEMS = [
    ("Manakah kebutuhan fungsional aplikasi tersebut?", ["Siswa dapat meminjam buku", "Warna layar harus biru", "Server harus ringan", "Font harus besar"], "A", "Kebutuhan fungsional menjelaskan tindakan yang dapat dilakukan pengguna."),
    ("Siapa yang perlu diwawancarai untuk memahami alur peminjaman?", ["Hanya vendor komputer", "Siswa dan petugas katalog", "Hanya penyedia internet", "Tidak perlu pengguna"], "B", "Siswa dan petugas merupakan pengguna dengan kebutuhan dan tanggung jawab berbeda."),
    ("Kriteria penerimaan mana yang paling dapat diuji?", ["Aplikasi terlihat bagus", "Aplikasi terasa modern", "Peminjaman ditolak ketika stok nol", "Semua orang suka aplikasi"], "C", "Kondisi stok nol dan penolakan peminjaman dapat diverifikasi secara konkret."),
    ("Di mana aturan stok tidak boleh negatif harus ditegakkan?", ["Hanya pada warna tombol", "Hanya pada petunjuk penggunaan", "Hanya pada browser", "Pada logika server dan integritas penyimpanan"], "D", "Server harus menjaga aturan data walaupun permintaan berasal dari klien yang berbeda."),
    ("Apa manfaat transaksi saat mencatat peminjaman dan mengurangi stok?", ["Kedua perubahan berhasil bersama atau dibatalkan bersama", "Menghilangkan kebutuhan pengujian", "Mengubah semua stok menjadi nol", "Menghapus riwayat peminjaman"], "A", "Transaksi menjaga catatan peminjaman dan stok tetap konsisten."),
    ("Apa tujuan memisahkan logika peminjaman dari tampilan?", ["Membuat aturan sulit ditemukan", "Memudahkan pemakaian ulang dan pengujian aturan", "Menonaktifkan validasi", "Menyimpan data di CSS"], "B", "Logika terpisah dapat diuji dan dipakai beberapa antarmuka tanpa menduplikasi aturan."),
    ("Kasus uji batas mana yang paling relevan untuk stok?", ["Nama aplikasi panjang", "Warna judul berubah", "Dua permintaan meminjam ketika stok tinggal satu", "Ukuran logo bertambah"], "C", "Permintaan bersamaan pada stok terakhir menguji konsistensi dan aturan stok."),
    ("Setelah memperbaiki fitur pengembalian, pengujian apa perlu dilakukan?", ["Hanya membuka beranda", "Menghapus semua pengujian", "Hanya memeriksa logo", "Uji pengembalian dan regresi peminjaman"], "D", "Regresi memastikan perbaikan tidak merusak alur peminjaman yang sudah berjalan."),
    ("Laporan bug mana yang paling membantu pengembang?", ["Langkah reproduksi, hasil aktual, dan hasil yang diharapkan", "Aplikasi jelek", "Tidak bekerja tanpa rincian", "Hanya nama pelapor"], "A", "Langkah dan hasil yang jelas membantu pengembang memahami serta memverifikasi perbaikan."),
]


def load_pack(version=VERSION):
    if version != VERSION:
        raise ValueError("Versi soal demo tidak tersedia.")
    return {"version": VERSION, "case": dict(CASE), "members": 3,
            "questions": [dict(id=i, text=text, options=dict(zip("ABCD", options)),
                               correct_answer=key, explanation=explanation, weight=10)
                          for i, (text, options, key, explanation) in enumerate(_ITEMS, 1)]}


def public_questions(pack):
    return [SimpleNamespace(id=q["id"], text=q["text"], weight=q["weight"],
                            **{f"option_{k.lower()}": v for k, v in q["options"].items()})
            for q in pack["questions"]]
