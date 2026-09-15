from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import HiddenField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class TeamForm(FlaskForm):
    team_code = StringField(
        "Kode Tim (Unik)",
        validators=[
            DataRequired(message="Kode tim wajib diisi."),
            Length(max=30, message="Kode tim maksimal 30 karakter."),
        ],
    )
    team_name = StringField(
        "Nama Tim",
        validators=[
            DataRequired(message="Nama tim wajib diisi."),
            Length(max=120, message="Nama tim maksimal 120 karakter."),
        ],
    )
    school = StringField(
        "Asal Sekolah",
        validators=[
            DataRequired(message="Asal sekolah wajib diisi."),
            Length(max=160, message="Asal sekolah maksimal 160 karakter."),
        ],
    )
    group_id = SelectField(
        "Kelompok / Group",
        coerce=int,
        validators=[DataRequired(message="Kelompok wajib dipilih.")],
    )
    submit = SubmitField("Simpan Data Tim")


class TeamCSVUploadForm(FlaskForm):
    file = FileField(
        "File CSV Tim (*.csv)",
        validators=[
            FileRequired(message="Silakan pilih file CSV terlebih dahulu."),
            FileAllowed(["csv"], message="Hanya file berekstensi .csv yang diperbolehkan."),
        ],
    )
    submit = SubmitField("Upload & Preview Data →")


class TeamImportConfirmForm(FlaskForm):
    file_token = HiddenField(validators=[DataRequired(message="Token file tidak valid.")])
    submit = SubmitField("Konfirmasi & Import ke Database")
