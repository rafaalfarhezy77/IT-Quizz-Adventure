from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import FloatField, HiddenField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import AnyOf, DataRequired, NumberRange


class CaseStudyForm(FlaskForm):
    title = StringField("Judul Study Case", validators=[DataRequired(message="Judul wajib diisi.")])
    description = TextAreaField("Deskripsi Study Case", validators=[DataRequired(message="Deskripsi wajib diisi.")])
    submit = SubmitField("SIMPAN STUDY CASE")


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


class NetworkingQuestionForm(QuestionForm):
    option_a = StringField("Pilihan A")
    option_b = StringField("Pilihan B")
    option_c = StringField("Pilihan C")
    option_d = StringField("Pilihan D")
    option_e = StringField("Pilihan E")
    correct_answer = StringField("Kunci jawaban utama", validators=[DataRequired()])
    stage = IntegerField("Tahap", validators=[DataRequired(), NumberRange(min=1, max=3)])
    question_type = SelectField("Tipe soal", choices=[("multiple_choice", "Pilihan Ganda"), ("true_false", "Benar/Salah"), ("short_text", "Isian Singkat")])
    case_study = TextAreaField("Studi kasus")
    accepted_answers_text = TextAreaField("Varian jawaban (satu per baris)")

    def apply_networking(self, question):
        question.stage = self.stage.data
        question.question_type = self.question_type.data
        question.option_e = self.option_e.data or None
        question.case_study = self.case_study.data or None
        question.accepted_answers = [a.strip() for a in (self.accepted_answers_text.data or "").splitlines() if a.strip()]

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        from types import SimpleNamespace
        from services.question_service import validate_networking_question
        q = SimpleNamespace(order_number=self.order_number.data, text=self.text.data, weight=self.weight.data, correct_answer=self.correct_answer.data, option_a=self.option_a.data, option_b=self.option_b.data, option_c=self.option_c.data, option_d=self.option_d.data)
        self.apply_networking(q)
        errors = validate_networking_question(q)
        self.correct_answer.errors.extend(errors)
        return not errors
