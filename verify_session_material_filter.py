"""Check rendered WTForms options against the actual session form JavaScript."""
import json
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

from flask import Flask, g
from forms.session import SessionForm
from models import db, Station, StationMode, QuestionSet, QuestionSetStatus
from routes.admin import _populate_session_form_choices


class OptionParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.options = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "option":
            attrs = dict(attrs)
            self.options.append({"value": attrs["value"], "textContent": "",
                                 "dataset": {"stationId": attrs["data-station-id"]}
                                 if "data-station-id" in attrs else {}})

    def handle_data(self, data):
        if self.options:
            self.options[-1]["textContent"] += data


class SessionMaterialFilterTest(unittest.TestCase):
    def test_all_stations_with_active_and_global_context(self):
        app = Flask(__name__)
        app.config.update(SECRET_KEY="test", WTF_CSRF_ENABLED=False,
                          SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        db.init_app(app)
        script = (Path(__file__).parent / "templates/admin/sessions/form.html").read_text(encoding="utf-8").split("<script>")[1].split("</script>")[0]
        runner = """
const fs = require('fs'), assert = require('assert');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
let change;
const station = {options:data.stations, selectedIndex:0, value:data.stations[0].value,
  addEventListener:(_, fn) => change = fn};
const material = {options:data.materials, value:data.materials[0].value,
  get selectedOptions() {return this.options.filter(o => o.value === this.value);}};
global.document = {getElementById:id => id === 'session_station_id' ? station : material};
eval(data.script);
data.stations.forEach((s, i) => {
  station.selectedIndex=i; station.value=s.value; change();
  const visible = material.options.filter(o => !o.hidden).map(o => o.value);
  assert.deepStrictEqual(visible, data.expected[s.value]);
  assert(visible.includes(material.value));
});
"""
        with app.test_request_context():
            db.create_all()
            stations = [Station(name=name, mode=StationMode.NORMAL, is_active=True)
                        for name in ["Software Engineering", "Networking", "Hardware", "Cyber Security"]]
            db.session.add_all(stations)
            db.session.flush()
            expected = {}
            for station in stations:
                expected[str(station.id)] = []
                for code in "ABCD":
                    qs = QuestionSet(station_id=station.id, code=code, name=f"Set {code}", status=QuestionSetStatus.READY)
                    db.session.add(qs)
                    db.session.flush()
                    expected[str(station.id)].append(str(qs.id))
                db.session.add(QuestionSet(station_id=station.id, code="DRAFT", name="Draft", status=QuestionSetStatus.DRAFT))
                db.session.add(QuestionSet(station_id=station.id, code="LOCKED", name="Locked", status=QuestionSetStatus.LOCKED))
            db.session.commit()
            expected[str(stations[2].id)] = ["0"]
            for active in [None, *stations]:
                with self.subTest(active=active.name if active else "Global"):
                    g.active_station = active
                    form = SessionForm()
                    _populate_session_form_choices(form)
                    payload = {"script": script, "stations": OptionParser(str(form.station_id())).options,
                               "materials": OptionParser(str(form.question_set_id())).options, "expected": expected}
                    result = subprocess.run(["node", "-e", runner], input=json.dumps(payload), text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
