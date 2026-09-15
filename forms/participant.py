from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class ParticipantAccessForm(FlaskForm):
    access_code = StringField(
        "Kode Akses",
        validators=[
            DataRequired(message="Kode akses wajib diisi."),
            Length(max=50, message="Kode akses maksimal 50 karakter."),
        ],
        render_kw={
            "placeholder": "Contoh: QUEST2026",
            "autocomplete": "off",
            "spellcheck": "false",
            "autofocus": True,
        },
    )
    submit = SubmitField("VERIFIKASI & MASUK")


class SelectionForm(FlaskForm):
    item_id = HiddenField(
        "Item ID",
        validators=[DataRequired(message="ID pilihan tidak boleh kosong.")],
    )


class ParticipantTeamForm(FlaskForm):
    team_name = StringField(
        "Nama Tim",
        render_kw={
            "placeholder": "Contoh: Garuda Cyber",
            "autocomplete": "off",
            "spellcheck": "false",
            "autofocus": True,
        },
    )
    school = StringField(
        "Asal Sekolah",
        render_kw={
            "placeholder": "Contoh: SMK Negeri 1 Surabaya",
            "autocomplete": "off",
            "spellcheck": "false",
        },
    )
    item_id = HiddenField("Item ID")
    submit = SubmitField("SIMPAN & LANJUTKAN")


class EmptyForm(FlaskForm):
    """Simple CSRF protection form for POST actions without text inputs."""
    pass
