from app import app
from models import Admin, Group, Station, db
from sqlalchemy import inspect


def verify():
    inspector = inspect(db.engine)
    expected_tables = {
        "admins", "stations", "groups", "teams", "question_sets",
        "questions", "sessions", "submissions", "answers", "scores",
    }
    assert expected_tables <= set(inspector.get_table_names())
    foreign_key_count = sum(
        len(inspector.get_foreign_keys(table)) for table in expected_tables
    )
    assert foreign_key_count == 11
    stations = db.session.scalars(db.select(Station).order_by(Station.name)).all()
    groups = db.session.scalars(db.select(Group).order_by(Group.code)).all()
    admins = db.session.scalars(db.select(Admin)).all()

    assert len(stations) == 4, f"Station seharusnya 4, ditemukan {len(stations)}"
    assert [group.code for group in groups] == ["A", "B", "C", "D"]
    assert len(admins) == 1, f"Admin seharusnya 1, ditemukan {len(admins)}"
    assert admins[0].password_hash != "admin123"
    assert admins[0].password_hash.startswith(("scrypt:", "pbkdf2:"))
    assert all(isinstance(station.question_sets, list) for station in stations)
    assert all(isinstance(group.teams, list) for group in groups)

    print("Foundation valid: 4 station, group A-D, 1 admin dengan password hash.")
    print("Schema valid: 10 tabel dan 11 foreign key ditemukan.")
    print("Relasi Station->QuestionSet dan Group->Team berhasil diakses.")


if __name__ == "__main__":
    with app.app_context():
        verify()
