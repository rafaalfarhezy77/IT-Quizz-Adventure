from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import FloatField, HiddenField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import AnyOf, DataRequired, NumberRange


class QuestionForm(FlaskForm):
    text = TextAreaField(
        "Teks Pertanyaan",
        validators=[DataRequired(message="Teks pertanyaan wajib diisi.")],
    )
    option_a = StringField(
        "Pilihan A",
        validators=[DataRequired(message="Pilihan A wajib diisi.")],
    )
    option_b = StringField(
        "Pilihan B",
        validators=[DataRequired(message="Pilihan B wajib diisi.")],
    )
    option_c = StringField(
        "Pilihan C",
        validators=[DataRequired(message="Pilihan C wajib diisi.")],
    )
    option_d = StringField(
        "Pilihan D",
        validators=[DataRequired(message="Pilihan D wajib diisi.")],
    )
    correct_answer = SelectField(
        "Kunci Jawaban",
        choices=[("A", "Pilihan A"), ("B", "Pilihan B"), ("C", "Pilihan C"), ("D", "Pilihan D")],
        validators=[
            DataRequired(message="Kunci jawaban wajib dipilih."),
            AnyOf(["A", "B", "C", "D"], message="Kunci jawaban harus berupa A, B, C, atau D."),
        ],
    )
    weight = FloatField(
        "Bobot Nilai / Skor",
        default=100.0,
        validators=[
            DataRequired(message="Bobot nilai wajib diisi."),
            NumberRange(min=0.01, message="Bobot nilai harus berupa angka positif lebih dari 0."),
        ],
    )
    order_number = IntegerField(
        "Nomor Urut",
        default=1,
        validators=[
            DataRequired(message="Nomor urut wajib diisi."),
            NumberRange(min=1, message="Nomor urut minimal bernilai 1."),
        ],
    )
    submit = SubmitField("Simpan Soal")


class QuestionSetStatusForm(FlaskForm):
    status = SelectField(
        "Status Question Set",
        choices=[
            ("DRAFT", "DRAFT — Tahap Penyusunan"),
            ("READY", "READY — Siap Digunakan"),
            ("LOCKED", "LOCKED — Terkunci / Sesi Berlangsung"),
        ],
        validators=[
            DataRequired(message="Status wajib dipilih."),
            AnyOf(["DRAFT", "READY", "LOCKED"], message="Status tidak valid."),
        ],
    )
    submit = SubmitField("Ubah Status")


class EmptyForm(FlaskForm):
    """Form kosong hanya untuk menyertakan CSRF token pada aksi POST (Delete, Restore, dsb)."""
    pass


class QuestionJSONUploadForm(FlaskForm):
    file = FileField(
        "File JSON Bank Soal (*.json)",
        validators=[
            FileRequired(message="Silakan pilih berkas JSON terlebih dahulu."),
            FileAllowed(["json"], message="Hanya file berekstensi .json yang diperbolehkan."),
        ],
    )
    station_id = SelectField(
        "Pos Perlombaan Target",
        coerce=int,
        validators=[DataRequired(message="Pos target wajib dipilih.")],
    )
    mode = SelectField(
        "Mode Import",
        choices=[
            ("ADD", "Tambah Soal Baru (ADD)"),
            ("UPDATE", "Perbarui Berdasarkan external_id (UPDATE)"),
        ],
        default="ADD",
        validators=[DataRequired(message="Mode import wajib dipilih.")],
    )
    submit = SubmitField("Upload & Preview Soal →")


class QuestionImportConfirmForm(FlaskForm):
    file_token = HiddenField(validators=[DataRequired(message="Token file tidak valid.")])
    station_id = HiddenField(validators=[DataRequired(message="ID Pos tidak valid.")])
    mode = HiddenField(validators=[DataRequired(message="Mode import tidak valid.")])
    submit = SubmitField("Konfirmasi & Import ke Database")

