import hashlib
import hmac
import secrets
from types import SimpleNamespace

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session, url_for, send_from_directory
from forms.participant import EmptyForm
from services import demo_service as store
from services.demo_questions import STATIONS, public_questions
from services.demo_packs import REGISTRY, load_pack, public_pack
from services.access_service import demo_enabled
from pathlib import Path

demo_bp = Blueprint("demo", __name__, url_prefix="/demo")


@demo_bp.context_processor
def demo_clock():
    return {"demo_now": store.now()}


@demo_bp.before_request
def check_enabled():
    if not demo_enabled():
        abort(404)


@demo_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@demo_bp.errorhandler(store.DemoError)
def demo_error(error):
    if request.is_json or request.endpoint == "demo.status":
        return jsonify(success=False, error=error.message), error.status
    return render_template("demo/page.html", demo_mode=True, page="error", message=error.message), error.status


def attempt(identifier, action=None, payload=None):
    return store.access_attempt(identifier, session.get("demo_owner", ""), action, payload)


def urls(identifier):
    return {name: url_for("demo." + name, identifier=identifier)
            for name in ("quiz", "case_study", "status", "answer", "advance", "begin_stage", "submit", "result")}


@demo_bp.get("/")
def select():
    session.setdefault("demo_owner", secrets.token_urlsafe(32))
    return render_template("demo/page.html", demo_mode=True, page="select", stations=REGISTRY,
                           attempts=store.resumable(session["demo_owner"]))


@demo_bp.get("/guide/<format>")
def guide(format):
    if format not in ("html", "pdf"):
        abort(404)
    folder = Path(__file__).resolve().parent.parent / "docs"
    return send_from_directory(folder, f"panduan_demo.{format}", as_attachment=format == "pdf")


@demo_bp.get("/software/rules", defaults={"slug": "software"})
@demo_bp.get("/<slug>/rules")
def rules(slug="software"):
    if slug not in REGISTRY:
        abort(404)
    session.setdefault("demo_owner", secrets.token_urlsafe(32))
    return render_template("demo/page.html", demo_mode=True, page="rules",
                           pack=load_pack(slug), slug=slug,
                           duration=current_app.config["DEMO_DURATION_SECONDS"] if slug == "software" else REGISTRY[slug]["duration"],
                           bonus_rate=current_app.config.get("TIME_BONUS_PER_SECOND", 1))


@demo_bp.post("/software/start", defaults={"slug": "software"})
@demo_bp.post("/<slug>/start")
def start(slug="software"):
    if slug not in REGISTRY:
        abort(404)
    owner = session.get("demo_owner")
    if not owner:
        raise store.DemoError("Buka aturan demo sebelum memulai.", 400)
    # Hash remote address; forwarded headers require hosting proxy configuration.
    ip_hash = hmac.new(str(current_app.secret_key).encode(),
                       (request.remote_addr or "unknown").encode(), hashlib.sha256).hexdigest()
    identifier = store.create_attempt(owner, ip_hash, slug)
    return redirect(url_for("demo.case_study" if slug in ("software", "hardware") else "demo.quiz", identifier=identifier))


@demo_bp.route("/<identifier>/case-study", methods=["GET", "POST"])
def case_study(identifier):
    a = attempt(identifier, "seen" if request.method == "POST" else None)
    if a["status"] != "RUNNING":
        return redirect(url_for("demo.result", identifier=identifier))
    if request.method == "POST":
        return redirect(url_for("demo.quiz", identifier=identifier))
    if not a["pack"].get("case"):
        return redirect(url_for("demo.quiz", identifier=identifier))
    return render_template("demo/page.html", demo_mode=True, page="case", a=a, links=urls(identifier))


@demo_bp.get("/<identifier>/quiz")
def quiz(identifier):
    a = attempt(identifier)
    if a["status"] != "RUNNING":
        return redirect(url_for("demo.result", identifier=identifier))
    if not a["seen"]:
        return redirect(url_for("demo.case_study", identifier=identifier))
    if a["pack"]["method"] == "networking" and a["state"]["awaiting_stage"]:
        return render_template("demo/page.html", demo_mode=True, page="transition", a=a, links=urls(identifier))
    if a["pack"]["method"] in ("networking", "hardware"):
        safe = public_pack(a["pack"])
        active_ids = {q["id"] for q in store.active_questions(a)}
        return render_template("demo/module.html", demo_mode=True, a=a, pack=safe, links=urls(identifier),
                               questions=[q for q in safe["questions"] if q["id"] in active_ids],
                               deadline=min(a["deadline"], a["state"]["stage_deadline"]) if safe["method"] == "networking" else a["deadline"])
    active = {q["id"] for q in store.active_questions(a)}
    questions = [q for q in public_questions(a["pack"]) if q.id in active]
    return render_template("participant/quiz.html", demo_mode=True, demo_attempt=a, demo_urls=urls(identifier),
                           station=SimpleNamespace(name=a["pack"]["name"]),
                           group=SimpleNamespace(code="DEMO"),
                           team=SimpleNamespace(team_code="DEMO", team_name="Simulasi satu tim"),
                           competition_session=SimpleNamespace(duration_seconds=a["pack"]["duration"]),
                           remaining_seconds=int(max(0, a["deadline"] - store.now())),
                           questions=questions, answers_map={int(k): v for k, v in a["answers"].items() if int(k) in active},
                           is_member_rotation=a["pack"]["method"] == "rotation", current_member=a["member"], total_members=a["pack"]["members"],
                           has_case_study=bool(a["pack"].get("case")), member_form=EmptyForm(), submit_form=EmptyForm())


@demo_bp.get("/<identifier>/status")
def status(identifier):
    a = attempt(identifier)
    deadline = a["deadline"]
    if a["pack"]["method"] == "networking" and not a["state"]["awaiting_stage"]:
        deadline = min(deadline, a["state"]["stage_deadline"])
    return jsonify(status="RUNNING" if a["status"] == "RUNNING" else "FINISHED",
                   remaining_seconds=int(max(0, deadline - store.now())),
                   deadline=deadline, server_time=store.now(), member=a["member"],
                   revision=a["revision"], stage=a["state"].get("stage"), awaiting_stage=a["state"].get("awaiting_stage", 0))


@demo_bp.post("/<identifier>/answer")
def answer(identifier):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise store.DemoError("Format request tidak valid.", 400)
    a = attempt(identifier, "answer", payload)
    return jsonify(success=True, member=a["member"], revision=a["revision"])


def form_payload():
    return {"member": request.form.get("member"), "revision": request.form.get("revision"), "stage": request.form.get("stage"),
            "components": {key[10:]: value for key, value in request.form.items() if key.startswith("component_") and value},
            "rationale": request.form.get("rationale", ""),
            "answers": {key[9:]: value for key, value in request.form.items() if key.startswith("question_")}}


@demo_bp.post("/<identifier>/advance")
def advance(identifier):
    a = attempt(identifier, "advance", form_payload())
    if a["status"] != "RUNNING":
        return redirect(url_for("demo.result", identifier=identifier))
    return render_template("demo/page.html", demo_mode=True, page="transition", a=a, links=urls(identifier))


@demo_bp.post("/<identifier>/begin-stage")
def begin_stage(identifier):
    attempt(identifier, "begin_stage", form_payload())
    return redirect(url_for("demo.quiz", identifier=identifier))


@demo_bp.post("/<identifier>/submit")
def submit(identifier):
    attempt(identifier, "submit", form_payload())
    return redirect(url_for("demo.result", identifier=identifier))


@demo_bp.get("/<identifier>/result")
def result(identifier):
    a = attempt(identifier)
    if a["status"] == "RUNNING":
        return redirect(url_for("demo.quiz", identifier=identifier))
    return render_template("demo/page.html", demo_mode=True, page="result", a=a)
