"""Verify permanent deletion using an isolated in-memory database."""
import re
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from models import (db, Admin, Group, Team, Station, CompetitionSession,
                    Submission, HardwareSubmission, HardwareSubmissionAudit,
                    NetworkingSubmission, NetworkingSubmissionAudit, Score, utcnow)
from routes.admin import admin_bp


def verify():
    app = Flask(__name__, template_folder="templates")
    app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://",
                      WTF_CSRF_ENABLED=True)
    db.init_app(app)
    CSRFProtect(app)
    app.register_blueprint(admin_bp)
    with app.app_context():
        db.create_all()
        db.session.execute(db.text("PRAGMA foreign_keys=ON"))
        admin = Admin(username="test", password_hash="test")
        group = Group(code="A")
        station = Station(name="Hardware")
        db.session.add_all([admin, group, station])
        db.session.flush()
        teams = [Team(team_code=str(i), team_name="Dummy", school="Test", group=group) for i in range(3)]
        competition = CompetitionSession(station=station, group=group, duration_seconds=600)
        db.session.add_all(teams + [competition])
        db.session.flush()
        for team in teams[:2]:
            sub = Submission(team=team, session=competition)
            db.session.add(sub)
            db.session.flush()
            hw = HardwareSubmission(submission=sub)
            net = NetworkingSubmission(submission=sub)
            db.session.add_all([hw, net, Score(submission=sub, submitted_at=utcnow())])
            db.session.flush()
            db.session.add_all([HardwareSubmissionAudit(hardware_submission=hw, action="test"),
                                NetworkingSubmissionAudit(networking_submission=net, action="test", reason="test")])
        db.session.commit()
        ids = [team.id for team in teams]
        client = app.test_client()
        with client.session_transaction() as session:
            session["admin_id"] = admin.id
        page = client.get("/admin/teams")
        assert page.status_code == 200
        token = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data).group(1).decode()
        endpoint = "/admin/teams/delete-permanent"
        assert client.post(endpoint, data={"team_ids": ids[:2]}).status_code == 400
        data = {"csrf_token": token, "team_ids": ids[:2], "confirmation": "HAPUS PERMANEN", "reason": ""}
        assert client.post(endpoint, data=data).status_code == 302
        assert db.session.query(Team).count() == 3
        data["reason"] = "Membersihkan dummy"
        data["team_ids"] = [ids[0], 99999]
        assert client.post(endpoint, data=data).status_code == 302
        assert db.session.query(Team).count() == 3
        data["team_ids"] = ids[:2]
        assert client.post(endpoint, data=data).status_code == 302
        assert db.session.query(Team).count() == 1
        for model in (Submission, Score, HardwareSubmission, HardwareSubmissionAudit,
                      NetworkingSubmission, NetworkingSubmissionAudit):
            assert db.session.query(model).count() == 0, model.__name__
        assert db.session.query(CompetitionSession).count() == 1
        assert db.session.get(Team, ids[2]) is not None
        data["team_ids"] = [ids[2]]
        assert client.post(endpoint, data=data).status_code == 302
        assert db.session.query(Team).count() == 0
    print("PASS: rendering, CSRF, required reason, atomic selection, bulk/single deletion, related history, preserved sessions")


if __name__ == "__main__":
    verify()
