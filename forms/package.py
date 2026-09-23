"""
Forms for Package and Group Mapping Management in Mythic 3.0.
"""
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    FloatField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL


class PackageActionForm(FlaskForm):
    """Form kosong bertoken CSRF untuk aksi status, duplikasi, dan hapus paket."""
    pass


class HardwarePackageForm(FlaskForm):
    """
    Form lengkap pembuatan & pengeditan Paket Tantangan Hardware Build (BuildCores).
    """
    # Informasi Umum
    station_id = SelectField("Pos Perlombaan", coerce=int, validators=[DataRequired(message="Pos wajib dipilih.")])
    package_code = StringField(
        "Kode Paket",
        validators=[DataRequired(message="Kode paket wajib diisi."), Length(max=30, message="Maksimal 30 karakter.")],
        render_kw={"placeholder": "Contoh: Paket 01"},
    )
    title = StringField(
        "Judul Tantangan",
        validators=[DataRequired(message="Judul wajib diisi."), Length(max=200, message="Maksimal 200 karakter.")],
        render_kw={"placeholder": "Contoh: Workstation AI & Deep Learning Entry-Level"},
    )
    description = TextAreaField(
        "Studi Kasus / Deskripsi",
        validators=[DataRequired(message="Deskripsi studi kasus wajib diisi.")],
        render_kw={"rows": 4, "placeholder": "Tuliskan kebutuhan klien, batasan penggunaan, dan tujuan build..."},
    )
    instructions = TextAreaField(
        "Petunjuk Pengerjaan",
        validators=[DataRequired(message="Petunjuk pengerjaan wajib diisi.")],
        render_kw={"rows": 3, "placeholder": "Langkah-langkah membuka BuildCores, memilih komponen, dan mengunggah bukti..."},
    )
    external_tool_url = StringField(
        "URL Alat Eksternal (BuildCores)",
        default="https://www.buildcores.com/",
        validators=[DataRequired(message="URL alat eksternal wajib diisi.")],
        render_kw={"placeholder": "https://www.buildcores.com/"},
    )
    duration_minutes = IntegerField(
        "Durasi Pengerjaan (Menit)",
        default=30,
        validators=[
            DataRequired(message="Durasi wajib diisi."),
            NumberRange(min=1, max=180, message="Durasi antara 1 hingga 180 menit."),
        ],
    )
    status = SelectField(
        "Status Paket",
        choices=[("DRAFT", "DRAFT (Konsep)"), ("ACTIVE", "ACTIVE (Aktif Siap Pakai)"), ("LOCKED", "LOCKED (Terkunci)"), ("ARCHIVED", "ARCHIVED (Diarsipkan)")],
        default="DRAFT",
    )

    # Batasan Build PC (Rules & Constraints)
    max_budget = FloatField(
        "Batas Budget Maksimal",
        default=1500.0,
        validators=[DataRequired(message="Batas budget wajib diisi."), NumberRange(min=0.01, message="Budget harus lebih dari 0.")],
    )
    currency = StringField("Mata Uang", default="USD", validators=[DataRequired(), Length(max=10)])
    region = StringField("Region", default="United States", validators=[Optional(), Length(max=50)])
    min_cpu_score = FloatField(
        "Target CPU Score Minimal",
        default=1000.0,
        validators=[DataRequired(), NumberRange(min=0, message="Skor minimal 0.")],
    )
    min_gpu_score = FloatField(
        "Target GPU Score Minimal",
        default=2000.0,
        validators=[DataRequired(), NumberRange(min=0, message="Skor minimal 0.")],
    )
    min_ram_gb = FloatField(
        "Kapasitas RAM Minimal (GB)",
        default=16.0,
        validators=[DataRequired(), NumberRange(min=1, message="RAM minimal 1 GB.")],
    )
    min_storage_gb = FloatField(
        "Kapasitas Storage Minimal (GB)",
        default=512.0,
        validators=[DataRequired(), NumberRange(min=1, message="Storage minimal 1 GB.")],
    )
    min_psu_watt = FloatField(
        "Daya PSU Minimal (Watt)",
        default=550.0,
        validators=[Optional(), NumberRange(min=0)],
    )
    required_components = TextAreaField(
        "Daftar Komponen Wajib",
        render_kw={"rows": 2, "placeholder": "Contoh: Dedicated GPU, NVMe M.2 SSD, Dual-Channel RAM"},
    )
    forbidden_components = TextAreaField(
        "Daftar Komponen Terlarang",
        render_kw={"rows": 2, "placeholder": "Contoh: Integrated GPU only, HDD sebagai boot drive, OEM unbranded PSU"},
    )
    used_parts_allowed = BooleanField("Boleh Komponen Bekas (Used Parts)", default=False)
    custom_price_allowed = BooleanField("Boleh Custom Price", default=False)
    discount_allowed = BooleanField("Boleh Diskon / Promosi", default=True)
    extra_notes = TextAreaField(
        "Catatan Tambahan Ketentuan",
        render_kw={"rows": 2, "placeholder": "Catatan khusus juri jika ada..."},
    )

    # Konfigurasi Pembobotan Penilaian (Total harus 100)
    weight_compatibility = FloatField("Bobot Kompatibilitas (%)", default=20.0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    weight_budget = FloatField("Bobot Kepatuhan Budget (%)", default=15.0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    weight_cpu_target = FloatField("Bobot Target CPU Score (%)", default=15.0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    weight_gpu_target = FloatField("Bobot Target GPU Score (%)", default=20.0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    weight_completeness = FloatField("Bobot Kelengkapan Komponen (%)", default=10.0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    weight_efficiency = FloatField("Bobot Efisiensi Harga/Performa (%)", default=15.0, validators=[DataRequired(), NumberRange(min=0, max=100)])
    weight_time_bonus = FloatField("Bobot Bonus Sisa Waktu (%)", default=5.0, validators=[DataRequired(), NumberRange(min=0, max=100)])

    submit = SubmitField("SIMPAN PAKET SOAL")


class PackageMappingForm(FlaskForm):
    """
    Form pemetaan paket soal kepada Kelompok A, B, C, D.
    Mendukung strategi SAME_FOR_ALL dan BY_GROUP.
    """
    strategy = SelectField(
        "Strategi Pemetaan",
        choices=[("SAME_FOR_ALL", "SAME_FOR_ALL (Semua kelompok mendapatkan paket yang sama)"), ("BY_GROUP", "BY_GROUP (Setiap kelompok dipasangkan dengan paket spesifik)")],
        default="BY_GROUP",
    )
    same_package_id = SelectField("Pilih Paket Bersama", coerce=int, validators=[Optional()])
    package_group_a = SelectField("Paket Kelompok A", coerce=int, validators=[Optional()])
    package_group_b = SelectField("Paket Kelompok B", coerce=int, validators=[Optional()])
    package_group_c = SelectField("Paket Kelompok C", coerce=int, validators=[Optional()])
    package_group_d = SelectField("Paket Kelompok D", coerce=int, validators=[Optional()])
    submit = SubmitField("SIMPAN PEMETAAN PAKET")
