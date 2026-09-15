from functools import wraps
from flask import session, redirect, url_for, flash
from models import Station, Group, Team

KEY_AUTHORIZED = "participant_authorized"
KEY_STATION_ID = "participant_station_id"
KEY_GROUP_ID = "participant_group_id"
KEY_TEAM_ID = "participant_team_id"
KEY_CONFIRMED = "participant_confirmed"
KEY_RULES_ACCEPTED = "participant_rules_accepted"

ALL_PARTICIPANT_KEYS = (
    KEY_AUTHORIZED,
    KEY_STATION_ID,
    KEY_GROUP_ID,
    KEY_TEAM_ID,
    KEY_CONFIRMED,
    KEY_RULES_ACCEPTED,
)


def clear_participant_session():
    """Clear only participant-related session data, preserving admin session."""
    for key in ALL_PARTICIPANT_KEYS:
        session.pop(key, None)


def clear_downstream_after_station():
    """Clear downstream selections when station is changed or reset."""
    session.pop(KEY_GROUP_ID, None)
    session.pop(KEY_TEAM_ID, None)
    session.pop(KEY_CONFIRMED, None)
    session.pop(KEY_RULES_ACCEPTED, None)


def clear_downstream_after_group():
    """Clear downstream selections when group is changed or reset."""
    session.pop(KEY_TEAM_ID, None)
    session.pop(KEY_CONFIRMED, None)
    session.pop(KEY_RULES_ACCEPTED, None)


def clear_downstream_after_team():
    """Clear downstream selections when team is changed or reset."""
    session.pop(KEY_CONFIRMED, None)
    session.pop(KEY_RULES_ACCEPTED, None)


def get_participant_context():
    """
    Fetch and validate the participant's current selection against the database.
    If any selected entity is invalid or deactivated, gracefully clears stale state.
    Returns a dict with resolved models and stage booleans.
    """
    authorized = bool(session.get(KEY_AUTHORIZED))
    if not authorized:
        return {
            "authorized": False,
            "station": None,
            "group": None,
            "team": None,
            "confirmed": False,
            "rules_accepted": False,
        }

    station_id = session.get(KEY_STATION_ID)
    station = None
    if station_id is not None:
        station = Station.query.filter_by(id=station_id, is_active=True).first()
        if not station:
            clear_downstream_after_station()
            session.pop(KEY_STATION_ID, None)

    group_id = session.get(KEY_GROUP_ID)
    group = None
    if station and group_id is not None:
        group = Group.query.filter_by(id=group_id).first()
        if not group:
            clear_downstream_after_group()
            session.pop(KEY_GROUP_ID, None)

    team_id = session.get(KEY_TEAM_ID)
    team = None
    if station and group and team_id is not None:
        team = Team.query.filter_by(id=team_id, is_active=True).first()
        if not team or team.group_id != group.id:
            clear_downstream_after_team()
            session.pop(KEY_TEAM_ID, None)
            team = None

    confirmed = bool(session.get(KEY_CONFIRMED)) and (team is not None)
    if not confirmed:
        session.pop(KEY_CONFIRMED, None)
        session.pop(KEY_RULES_ACCEPTED, None)

    rules_accepted = bool(session.get(KEY_RULES_ACCEPTED)) and confirmed
    if not rules_accepted:
        session.pop(KEY_RULES_ACCEPTED, None)

    return {
        "authorized": authorized,
        "station": station,
        "group": group,
        "team": team,
        "confirmed": confirmed,
        "rules_accepted": rules_accepted,
    }


def get_next_required_participant_endpoint():
    """Determine the next endpoint the participant must visit based on state."""
    ctx = get_participant_context()
    if not ctx["authorized"]:
        return "participant.access"
    if not ctx["station"]:
        return "participant.station_select"
    if not ctx["group"]:
        return "participant.group_select"
    if not ctx["team"]:
        return "participant.team_select"
    if not ctx["confirmed"]:
        return "participant.confirm"
    if not ctx["rules_accepted"]:
        return "participant.rules"
    return "participant.waiting"


def require_participant_stage(stage_name):
    """
    Decorator to enforce prerequisite stages for participant views.
    Allowed stage_name: 'authorized', 'station', 'group', 'team', 'confirmed', 'rules_accepted'
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ctx = get_participant_context()
            if not ctx["authorized"]:
                flash("Silakan masukkan kode akses peserta terlebih dahulu.", "warning")
                return redirect(url_for("participant.access"))

            if stage_name in ("station", "group", "team", "confirmed", "rules_accepted") and not ctx["station"]:
                flash("Silakan pilih pos perlombaan terlebih dahulu.", "warning")
                return redirect(url_for("participant.station_select"))

            if stage_name in ("group", "team", "confirmed", "rules_accepted") and not ctx["group"]:
                flash("Silakan pilih kelompok terlebih dahulu.", "warning")
                return redirect(url_for("participant.group_select"))

            if stage_name in ("team", "confirmed", "rules_accepted") and not ctx["team"]:
                flash("Silakan pilih tim terlebih dahulu.", "warning")
                return redirect(url_for("participant.team_select"))

            if stage_name in ("confirmed", "rules_accepted") and not ctx["confirmed"]:
                flash("Silakan konfirmasi identitas tim terlebih dahulu.", "warning")
                return redirect(url_for("participant.confirm"))

            if stage_name == "rules_accepted" and not ctx["rules_accepted"]:
                flash("Silakan baca dan setujui aturan lomba terlebih dahulu.", "warning")
                return redirect(url_for("participant.rules"))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
