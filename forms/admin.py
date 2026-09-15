from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(message="Username wajib diisi."), Length(max=80)])
    password = PasswordField("Password", validators=[DataRequired(message="Password wajib diisi."), Length(max=256)])
    submit = SubmitField("Login ke dashboard")
