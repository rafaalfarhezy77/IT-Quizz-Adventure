"""
Forms for Participant Hardware Challenge Submission and Committee Review in Mythic 3.0.
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    FloatField,
    HiddenField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class HardwareSubmissionForm(FlaskForm):
    """
    Form pengumpulan hasil pengerjaan Build PC via BuildCores oleh peserta.
    """
    buildcores_url = StringField(
        "URL Hasil Konfigurasi BuildCores",
        validators=[
            DataRequired(message="URL BuildCores wajib diisi."),
            Length(max=500, message="URL terlalu panjang (maks 500 karakter)."),
        ],
        render_kw={"placeholder": "https://www.buildcores.com/builds/... atau https://www.buildcores.com/..."},
    )
    total_price = FloatField(
        "Total Harga Build ($ / USD)",
        validators=[
            DataRequired(message="Total harga wajib diisi."),
            NumberRange(min=0.01, message="Total harga harus lebih besar dari 0."),
        ],
        render_kw={"placeholder": "Contoh: 1420.50", "step": "0.01"},
    )
    cpu_name = StringField(
        "Nama Processor (CPU)",
        validators=[DataRequired(message="Nama CPU wajib diisi."), Length(max=150)],
        render_kw={"placeholder": "Contoh: AMD Ryzen 5 7600X / Intel Core i5-13600K"},
    )
    cpu_score = FloatField(
        "CPU Benchmark Score",
        validators=[
            DataRequired(message="Skor CPU wajib diisi."),
            NumberRange(min=0, message="Skor tidak boleh negatif."),
        ],
        render_kw={"placeholder": "Contoh: 1250", "step": "any"},
    )
    gpu_name = StringField(
        "Nama Kartu Grafis (GPU)",
        validators=[DataRequired(message="Nama GPU wajib diisi."), Length(max=150)],
        render_kw={"placeholder": "Contoh: NVIDIA GeForce RTX 4060 Ti 16GB"},
    )
    gpu_score = FloatField(
        "GPU Benchmark Score",
        validators=[
            DataRequired(message="Skor GPU wajib diisi."),
            NumberRange(min=0, message="Skor tidak boleh negatif."),
        ],
        render_kw={"placeholder": "Contoh: 2850", "step": "any"},
    )
    ram_capacity_gb = FloatField(
        "Kapasitas RAM Total (GB)",
        validators=[
            DataRequired(message="Kapasitas RAM wajib diisi."),
            NumberRange(min=1, message="RAM minimal 1 GB."),
        ],
        render_kw={"placeholder": "Contoh: 32", "step": "any"},
    )
    storage_capacity_gb = FloatField(
        "Kapasitas Penyimpanan Total (GB)",
        validators=[
            DataRequired(message="Kapasitas storage wajib diisi."),
            NumberRange(min=1, message="Storage minimal 1 GB (1 TB = 1000/1024 GB)."),
        ],
        render_kw={"placeholder": "Contoh: 1000", "step": "any"},
    )
    psu_name = StringField(
        "Nama & Daya Power Supply (PSU)",
        validators=[DataRequired(message="Nama PSU wajib diisi."), Length(max=150)],
        render_kw={"placeholder": "Contoh: Corsair RM750e 750W 80+ Gold"},
    )
    components_summary = TextAreaField(
        "Daftar / Ringkasan Komponen Lengkap",
        validators=[DataRequired(message="Daftar komponen wajib diisi.")],
        render_kw={"rows": 4, "placeholder": "Motherboard, Cooler, Casing, dan komponen pendukung lainnya..."},
    )
    build_rationale = TextAreaField(
        "Penjelasan Singkat Alasan Memilih Build",
        validators=[DataRequired(message="Penjelasan alasan memilih build wajib diisi.")],
        render_kw={"rows": 3, "placeholder": "Jelaskan mengapa konfigurasi ini paling optimal untuk studi kasus yang diberikan..."},
    )
    screenshot = FileField(
        "Unggah Screenshot Hasil BuildCores",
        validators=[
            Optional(),
            FileAllowed(["png", "jpg", "jpeg", "webp"], "Hanya berkas gambar (PNG, JPG, WebP) yang diizinkan!"),
        ],
    )
    confirmation_checked = BooleanField(
        "Saya menyatakan dengan sungguh-sungguh bahwa data yang dikirim sesuai dengan konfigurasi di BuildCores.",
        validators=[DataRequired(message="Anda wajib menyetujui pernyataan kesesuaian data.")],
    )
    submit = SubmitField("KIRIM HASIL PENGERJAAN")


class HardwareReviewForm(FlaskForm):
    """
    Form pemeriksaan dan koreksi hasil pengerjaan Pos Hardware oleh panitia.
    """
    is_compatible = SelectField(
        "Status Kompatibilitas",
        choices=[("1", "KOMPATIBEL (Memenuhi Syarat)"), ("0", "TIDAK KOMPATIBEL (Ada Isu / Masalah)")],
        default="1",
    )
    corrected_price = FloatField("Koreksi Total Harga ($)", validators=[Optional(), NumberRange(min=0)])
    corrected_cpu_score = FloatField("Koreksi CPU Score", validators=[Optional(), NumberRange(min=0)])
    corrected_gpu_score = FloatField("Koreksi GPU Score", validators=[Optional(), NumberRange(min=0)])
    reviewer_notes = TextAreaField("Catatan Juri / Panitia", render_kw={"rows": 3, "placeholder": "Tuliskan catatan atau evaluasi juri..."})
    reason = TextAreaField("Alasan Perubahan / Keputusan", render_kw={"rows": 2, "placeholder": "Alasan koreksi nilai atau perubahan status..."})
    action = HiddenField("Action", default="VERIFY")
    submit = SubmitField("PROSES VERIFIKASI")
