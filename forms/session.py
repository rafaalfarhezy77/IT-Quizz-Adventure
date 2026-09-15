from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class SessionForm(FlaskForm):
    station_id = SelectField(
        "Pos Perlombaan",
        coerce=int,
        validators=[DataRequired(message="Pos perlombaan wajib dipilih.")],
    )
    group_id = SelectField(
        "Kelompok Peserta",
        coerce=int,
        validators=[DataRequired(message="Kelompok wajib dipilih.")],
    )
    question_set_id = SelectField(
        "Bank Soal",
        coerce=int,
        validators=[DataRequired(message="Bank soal wajib dipilih.")],
    )
    duration_minutes = IntegerField(
        "Durasi Pengerjaan (Menit)",
        default=10,
        validators=[
            DataRequired(message="Durasi pengerjaan wajib diisi."),
            NumberRange(min=1, max=180, message="Durasi harus antara 1 sampai 180 menit."),
        ],
    )
    submit = SubmitField("SIMPAN SESI LOMBA")


class SessionActionForm(FlaskForm):
    """CSRF protection form for session state transition actions (Start, Finish, Cancel)."""
    pass
