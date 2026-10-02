"""Transactional demo storage independent from official competition records."""
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from flask import current_app
from services.demo_packs import load_pack, REGISTRY
from services.quiz_service import partition_questions_for_members
from services.score_math import answer_points, time_bonus
from services.networking_service import evaluate_short_text_answer
from services.hardware_scoring_service import calculate_hardware_scores


class DemoError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


def now():
    return time.time()


@contextmanager
def connection():
    path = Path(current_app.config["DEMO_DATABASE_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, ip_hash TEXT NOT NULL,
            created REAL NOT NULL, deadline REAL NOT NULL, expires REAL NOT NULL,
            pack TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '{}',
            member INTEGER NOT NULL DEFAULT 1, seen INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'RUNNING', result TEXT,
            revision INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT '{}')""")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(attempts)")}
        for name, definition in (("revision", "INTEGER NOT NULL DEFAULT 0"), ("state", "TEXT NOT NULL DEFAULT '{}'")):
            if name not in columns:
                conn.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
        for name, column in (("owner_created", "owner, created"), ("ip_created", "ip_hash, created"), ("expires", "expires")):
            conn.execute(f"CREATE INDEX IF NOT EXISTS demo_{name} ON attempts({column})")


def cleanup():
    with connection() as conn:
        return conn.execute("DELETE FROM attempts WHERE expires <= ?", (now(),)).rowcount


def create_attempt(owner, ip_hash, slug="software"):
    try:
        pack = load_pack(slug)
    except (ValueError, FileNotFoundError):
        raise DemoError("Soal latihan belum tersedia. Silakan coba kembali nanti.", 503)
    if slug != "hardware" and not pack["questions"]:
        raise DemoError("Soal latihan belum tersedia. Silakan coba kembali nanti.", 503)
    pack["duration"] = current_app.config["DEMO_DURATION_SECONDS"] if slug == "software" else REGISTRY[slug]["duration"]
    pack["bonus_rate"] = float(current_app.config.get("TIME_BONUS_PER_SECOND", 1))
    pack["supports_revision"] = True
    with connection() as conn:
        timestamp = now()
        conn.execute("DELETE FROM attempts WHERE expires <= ?", (timestamp,))
        for column, value, limit in (("owner", owner, current_app.config["DEMO_STARTS_PER_HOUR"]),
                                     ("ip_hash", ip_hash, current_app.config["DEMO_IP_STARTS_PER_HOUR"] )):
            count = conn.execute(f"SELECT count(*) FROM attempts WHERE {column}=? AND created>?", (value, timestamp - 3600)).fetchone()[0]
            if count >= limit:
                raise DemoError("Batas percobaan tercapai. Coba kembali dalam satu jam.", 429)
        if conn.execute("SELECT count(*) FROM attempts").fetchone()[0] >= current_app.config["DEMO_MAX_ATTEMPTS"]:
            raise DemoError("Demo sedang penuh. Silakan coba kembali nanti.", 503)
        identifier = "demo_" + secrets.token_urlsafe(24)
        state = {"stage": 1, "stage_deadline": timestamp + 90, "awaiting_stage": 0} if slug == "networking" else {}
        conn.execute("""INSERT INTO attempts(id,owner,ip_hash,created,deadline,expires,pack,state,seen)
                        VALUES(?,?,?,?,?,?,?,?,?)""", (identifier, owner, ip_hash, timestamp,
                        timestamp + pack["duration"], timestamp + current_app.config["DEMO_TTL_SECONDS"],
                        json.dumps(pack), json.dumps(state), int(not pack.get("case"))))
    return identifier


def _decode(row):
    a = dict(row)
    for key in ("pack", "answers", "result", "state"):
        a[key] = json.loads(a[key]) if a[key] else None
    for key, value in dict(slug="software", name="Software Engineering", method="rotation").items():
        a["pack"].setdefault(key, value)
    return a


def hardware_evaluation(pack, state, remaining):
    chosen = state.get("components", {})
    items = {cat: next((i for i in options if i["id"] == chosen.get(cat)), {}) for cat, options in pack["catalogue"].items()}
    watts = items["cpu"].get("watts", 0) + items["gpu"].get("watts", 0) + 100
    checks = {
        "socket": bool(items["cpu"] and items["motherboard"]) and items["cpu"].get("socket") == items["motherboard"].get("socket"),
        "ram": bool(items["ram"] and items["motherboard"]) and items["ram"].get("ram_type") == items["motherboard"].get("ram_type"),
        "psu": bool(items["psu"]) and items["psu"].get("watts", 0) >= watts,
    }
    data = dict(total_price=sum(i.get("price", 0) for i in items.values()),
                cpu_name=items["cpu"].get("name", ""), cpu_score=items["cpu"].get("score", 0),
                gpu_name=items["gpu"].get("name", ""), gpu_score=items["gpu"].get("score", 0),
                ram_capacity_gb=items["ram"].get("capacity", 0), storage_capacity_gb=items["storage"].get("capacity", 0),
                psu_name=items["psu"].get("name", ""), is_compatible=all(items.values()) and all(checks.values()))
    raw, bonus, final, breakdown = calculate_hardware_scores(data, pack["rules"], pack["scoring"], remaining,
                                                          pack["duration"], is_admin_verified=True)
    breakdown["is_admin_verified"] = False
    return dict(raw_score=raw, time_bonus=bonus, final_score=final, breakdown=breakdown, checks=checks,
                items=items, total_price=data["total_price"], power_required=watts,
                example={cat: options[0] for cat, options in pack["catalogue"].items()})


def _finish(a, timestamp, timeout=False):
    pack = a["pack"]
    remaining = 0 if timeout else int(max(0, a["deadline"] - timestamp))
    if pack["method"] == "hardware":
        result = hardware_evaluation(pack, a["state"], remaining)
    else:
        stage_scores = {1: 0.0, 2: 0.0, 3: 0.0}
        correct_stage3, raw = 0, 0.0
        for q in pack["questions"]:
            selected = a["answers"].get(str(q["id"]), "")
            if q.get("kind") == "short_text":
                correct, _ = evaluate_short_text_answer(selected, [q["correct_answer"], *q.get("accepted", [])])
                points = float(q["weight"]) if correct else 0
            else:
                correct, points = answer_points(selected, q["correct_answer"], q["weight"])
            raw += points
            stage_scores[q.get("stage", 1)] += points
            correct_stage3 += int(correct and q.get("stage") == 3)
        bonus = time_bonus(remaining, pack["bonus_rate"])
        result = dict(raw_score=round(raw, 2), time_bonus=bonus, final_score=round(raw + bonus, 2))
        if pack["method"] == "networking":
            result.update(stage_scores=stage_scores, correct_stage3=correct_stage3, has_stamp=correct_stage3 >= 4, penalty=0)
    result["submitted_at"] = timestamp
    a["status"], a["result"] = ("TIMED_OUT" if timeout else "SUBMITTED"), result


def _persist(conn, a):
    a["revision"] += 1
    conn.execute("UPDATE attempts SET answers=?,member=?,seen=?,status=?,result=?,revision=?,state=? WHERE id=?",
                 (json.dumps(a["answers"]), a["member"], a["seen"], a["status"], json.dumps(a["result"]),
                  a["revision"], json.dumps(a["state"]), a["id"]))


def active_questions(a):
    pack = a["pack"]
    if pack["method"] == "rotation":
        return partition_questions_for_members(pack["questions"], pack["members"])[a["member"]]
    if pack["method"] == "networking":
        return [] if a["state"]["awaiting_stage"] else [q for q in pack["questions"] if q["stage"] == a["state"]["stage"]]
    return pack["questions"]


def _expire(a, timestamp):
    if a["status"] != "RUNNING":
        return False
    if timestamp >= a["deadline"]:
        _finish(a, a["deadline"], True)
        return True
    if a["pack"]["method"] == "networking" and not a["state"]["awaiting_stage"] and timestamp >= a["state"]["stage_deadline"]:
        if a["state"]["stage"] == 3:
            _finish(a, a["state"]["stage_deadline"], True)
        else:
            a["state"]["awaiting_stage"] = a["state"]["stage"] + 1
        return True
    return False


def _mutate(a, action, payload, timestamp):
    if action == "seen":
        a["seen"] = 1
        return
    if a["pack"].get("supports_revision") and str(payload.get("revision")) != str(a["revision"]):
        raise DemoError("Progres berubah di tab lain. Muat ulang halaman sebelum melanjutkan.")
    if not a["seen"]:
        raise DemoError("Baca studi kasus terlebih dahulu.")
    if str(payload.get("member")) != str(a["member"]):
        raise DemoError("Giliran anggota sudah berubah. Muat ulang halaman.")
    method = a["pack"]["method"]
    if method == "networking":
        if action == "begin_stage" and a["state"]["awaiting_stage"]:
            stage = a["state"]["awaiting_stage"]
            a["state"].update(stage=stage, awaiting_stage=0,
                              stage_deadline=min(a["deadline"], timestamp + a["pack"]["stage_seconds"][stage - 1]))
            return
        if a["state"]["awaiting_stage"] or str(payload.get("stage")) != str(a["state"]["stage"]):
            raise DemoError("Tahap berubah atau sudah terkunci. Muat ulang halaman.")
    if action == "begin_stage":
        raise DemoError("Tidak ada tahap yang menunggu konfirmasi.")
    if method == "hardware":
        components, rationale = payload.get("components", {}), payload.get("rationale", "")
        if not isinstance(components, dict) or not isinstance(rationale, str) or len(rationale) > 1000:
            raise DemoError("Format rakitan tidak valid.", 400)
        for cat, identifier in components.items():
            if cat not in a["pack"]["catalogue"] or identifier not in [i["id"] for i in a["pack"]["catalogue"][cat]]:
                raise DemoError("Komponen bukan dari katalog latihan.", 400)
        if action == "advance":
            raise DemoError("Hardware tidak menggunakan rotasi.")
        if action == "submit" and (len(components) != 6 or not rationale.strip()):
            raise DemoError("Pilih enam komponen dan tulis alasan singkat sebelum submit.", 400)
        a["state"].update(components=components, rationale=rationale.strip())
    else:
        answers = payload.get("answers", {})
        if not isinstance(answers, dict) or len(answers) > len(a["pack"]["questions"]):
            raise DemoError("Format jawaban tidak valid.", 400)
        questions = {str(q["id"]): q for q in active_questions(a)}
        cleaned = {}
        for key, value in answers.items():
            q = questions.get(key)
            if not q or not isinstance(value, str):
                raise DemoError("Soal tidak termasuk dalam giliran/tahap aktif.", 400)
            if q.get("kind") == "short_text":
                if len(value) > 255:
                    raise DemoError("Jawaban singkat maksimal 255 karakter.", 400)
                cleaned[key] = value.strip()
            elif value not in q["options"]:
                raise DemoError("Pilihan jawaban tidak tersedia.", 400)
            else:
                cleaned[key] = value
        if method == "networking" and a["state"]["stage"] in (1, 2):
            pending = [key for key in questions if key not in a["answers"]]
            for key, value in cleaned.items():
                if key in a["answers"]:
                    if value != a["answers"][key]:
                        raise DemoError("Jawaban tahap ini sudah dikunci.")
                elif not pending or key != pending.pop(0):
                    raise DemoError("Jawab soal yang sedang aktif sebelum melanjutkan.")
        if action == "submit" and method == "rotation" and a["member"] != a["pack"]["members"]:
            raise DemoError("Selesaikan giliran setiap anggota terlebih dahulu.")
        if action == "submit" and method == "networking" and a["state"]["stage"] != 3:
            raise DemoError("Selesaikan seluruh tahap terlebih dahulu.")
        if action == "advance" and method == "networking" and a["state"]["stage"] < 3 and not all(key in a["answers"] or key in cleaned for key in questions):
            raise DemoError("Jawab seluruh soal tahap ini terlebih dahulu.")
        a["answers"].update(cleaned)
    if action == "advance":
        if method == "rotation" and a["member"] < a["pack"]["members"]:
            a["member"] += 1
        elif method == "networking" and a["state"]["stage"] < 3:
            a["state"]["awaiting_stage"] = a["state"]["stage"] + 1
        else:
            raise DemoError("Seluruh giliran atau tahap sudah selesai.")
    elif action == "submit":
        _finish(a, timestamp)


def access_attempt(identifier, owner, action=None, payload=None):
    error = None
    with connection() as conn:
        timestamp = now()
        row = conn.execute("SELECT * FROM attempts WHERE id=? AND owner=?", (identifier, owner)).fetchone()
        if not row or not identifier.startswith("demo_"):
            raise DemoError("Sesi demo tidak ditemukan atau bukan milik browser ini.", 404)
        a = _decode(row)
        if timestamp >= a["expires"]:
            raise DemoError("Sesi demo kedaluwarsa. Mulai percobaan baru.", 410)
        if _expire(a, timestamp):
            _persist(conn, a)
        if action:
            if a["status"] != "RUNNING":
                if action != "submit":
                    error = DemoError("Jawaban sudah dikunci karena sesi selesai.")
            else:
                try:
                    _mutate(a, action, payload or {}, timestamp)
                    _persist(conn, a)
                except DemoError as exc:
                    error = exc
    if error:
        raise error
    return a


def resumable(owner):
    with connection() as conn:
        rows = conn.execute("SELECT * FROM attempts WHERE owner=? AND status='RUNNING' AND expires>? AND deadline>? ORDER BY created DESC", (owner, now(), now())).fetchall()
    return [_decode(row) for row in rows]


def statistics():
    with connection() as conn:
        rows = conn.execute("SELECT pack,status,deadline FROM attempts WHERE expires>?", (now(),)).fetchall()
    stats = {slug: dict(name=meta["name"], active=0, finished=0) for slug, meta in REGISTRY.items()}
    for row in rows:
        slug = json.loads(row["pack"]).get("slug", "software")
        if slug in stats:
            key = "active" if row["status"] == "RUNNING" and row["deadline"] > now() else "finished"
            stats[slug][key] += 1
    return list(stats.values())
