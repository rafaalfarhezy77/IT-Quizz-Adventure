"""Validated Hardware package import; one database transaction per file."""
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from models import ChallengePackage, PackageStatus, Station, db
from services.package_service import create_package, update_package, is_package_editable, validate_scoring_weights

WEIGHTS = ("weight_compatibility", "weight_budget", "weight_cpu_target", "weight_gpu_target",
           "weight_completeness", "weight_efficiency", "weight_time_bonus")
RULE_NUMBERS = {"max_budget": .01, "min_cpu_score": 0, "min_gpu_score": 0, "min_ram_gb": 1, "min_storage_gb": 1}
RULE_TEXT = {"region": "United States", "required_components": "", "forbidden_components": "", "extra_notes": ""}
RULE_BOOL = {"used_parts_allowed": False, "custom_price_allowed": False, "discount_allowed": True}
PACKAGE_FIELDS = {"package_code", "title", "description", "instructions", "external_tool_url", "duration_minutes", "rules_config", "scoring_config"}


def _reject_constant(value):
    raise ValueError(f"Angka {value} tidak valid dalam JSON.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Kunci JSON '{key}' duplikat.")
        result[key] = value
    return result


def parse_hardware_json(path: Path, station_id: int, mode: str = "ADD") -> dict:
    result = {"is_valid": False, "errors": [], "rows": [], "mode": mode}
    station = db.session.get(Station, station_id, populate_existing=True)
    if not station or not station.is_active or station.name.strip().lower() != "hardware":
        result["errors"].append("Target harus Pos Hardware yang aktif.")
        return result
    if mode not in ("ADD", "UPDATE"):
        result["errors"].append("Mode impor harus ADD atau UPDATE.")
        return result
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("Ukuran file maksimal 5 MB.")
        data = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        result["errors"].append(f"File tidak dapat dibaca: {error}")
        return result
    if not isinstance(data, dict) or data.get("station") != "Hardware":
        result["errors"].append("Root wajib berupa object dengan station: Hardware.")
        return result
    if set(data) - {"station", "packages"}:
        result["errors"].append("Root hanya mendukung station dan packages.")
    packages = data.get("packages")
    if not isinstance(packages, list) or not packages:
        result["errors"].append("packages wajib berupa array paket yang tidak kosong.")
        return result
    existing = {}
    for package in db.session.scalars(db.select(ChallengePackage).where(ChallengePackage.station_id == station_id).execution_options(populate_existing=True)):
        existing.setdefault(package.package_code.strip().casefold(), []).append(package)
    seen = set()
    for index, raw in enumerate(packages, 1):
        errors = []
        normalized = {}
        row = {"index": index, "data": normalized, "errors": errors, "existing_id": None, "status": "DRAFT", "action": mode}
        result["rows"].append(row)
        if not isinstance(raw, dict):
            errors.append("Paket wajib berupa object.")
            continue
        if set(raw) - PACKAGE_FIELDS:
            errors.append("Field paket tidak dikenal: " + ", ".join(sorted(set(raw) - PACKAGE_FIELDS)))

        def text(source, key, maximum=None, default=None):
            value = source.get(key, default)
            if not isinstance(value, str) or (default is None and not value.strip()):
                errors.append(f"{key}: wajib berupa teks{' tidak kosong' if default is None else ''}.")
                return ""
            value = value.strip()
            if maximum and len(value) > maximum:
                errors.append(f"{key}: maksimal {maximum} karakter.")
            return value

        def number(source, key, minimum, maximum=None):
            value = source.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{key}: wajib berupa angka JSON.")
                return 0
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite or value < minimum or (maximum is not None and value > maximum):
                errors.append(f"{key}: angka harus finite, minimal {minimum}" + (f", maksimal {maximum}." if maximum is not None else "."))
                return 0
            return value

        for key, limit in (("package_code", 30), ("title", 200), ("description", None), ("instructions", None), ("external_tool_url", 500)):
            normalized[key] = text(raw, key, limit)
        try:
            url = urlsplit(normalized["external_tool_url"])
            if url.scheme not in ("http", "https") or not url.hostname or url.username or any(char.isspace() for char in normalized["external_tool_url"]):
                raise ValueError()
            url.port
        except ValueError:
            errors.append("external_tool_url: gunakan URL HTTP/HTTPS yang valid.")
        duration = number(raw, "duration_minutes", 1, 180)
        if not isinstance(raw.get("duration_minutes"), int) or isinstance(raw.get("duration_minutes"), bool):
            errors.append("duration_minutes: wajib bilangan bulat 1–180.")
        normalized["duration_minutes"] = duration
        key = normalized["package_code"].casefold()
        if key in seen:
            errors.append("package_code: kode duplikat di dalam file.")
        seen.add(key)
        matches = existing.get(key, [])
        if len(matches) > 1:
            errors.append("package_code: ditemukan beberapa paket dengan kode yang ambigu di database.")
        elif mode == "ADD" and matches:
            errors.append("package_code: sudah tersedia; gunakan UPDATE.")
        elif mode == "UPDATE":
            if not matches:
                errors.append("package_code: paket UPDATE tidak ditemukan.")
            else:
                package = matches[0]
                row.update(existing_id=package.id, status=package.status.value)
                normalized["package_code"] = package.package_code
                if package.challenge_type != "hardware_build_challenge":
                    errors.append("Paket existing bukan tantangan Hardware.")
                editable, reason = is_package_editable(package)
                if not editable:
                    errors.append(reason)
        rules = raw.get("rules_config")
        if not isinstance(rules, dict):
            errors.append("rules_config: wajib berupa object.")
            rules = {}
        rule_keys = set(RULE_NUMBERS) | set(RULE_TEXT) | set(RULE_BOOL) | {"currency", "min_psu_watt"}
        if set(rules) - rule_keys:
            errors.append("rules_config: field tidak dikenal: " + ", ".join(sorted(set(rules) - rule_keys)))
        config = {key: number(rules, key, minimum) for key, minimum in RULE_NUMBERS.items()}
        config["currency"] = text(rules, "currency", 10)
        for key, default in RULE_TEXT.items():
            config[key] = text(rules, key, 50 if key == "region" else None, default)
        for key, default in RULE_BOOL.items():
            value = rules.get(key, default)
            if not isinstance(value, bool):
                errors.append(f"{key}: wajib true atau false, bukan teks/angka.")
            config[key] = value
        config["min_psu_watt"] = number(rules, "min_psu_watt", 0) if rules.get("min_psu_watt") is not None else None
        config["budget_max"] = config["max_budget"]
        normalized["rules_config"] = config
        scoring = raw.get("scoring_config")
        if not isinstance(scoring, dict):
            errors.append("scoring_config: wajib berupa object.")
            scoring = {}
        if set(scoring) - set(WEIGHTS):
            errors.append("scoring_config: gunakan hanya tujuh nama bobot pada template.")
        config = {key: number(scoring, key, 0, 100) for key in WEIGHTS}
        valid, reason = validate_scoring_weights(config)
        if not valid:
            errors.append(reason)
        config.update(weight_cpu=config["weight_cpu_target"], weight_gpu=config["weight_gpu_target"])
        normalized["scoring_config"] = config
    result["is_valid"] = not result["errors"] and all(not row["errors"] for row in result["rows"])
    return result


def execute_hardware_import(path: Path, station_id: int, mode: str) -> tuple[bool, int, str | None]:
    validation = parse_hardware_json(path, station_id, mode)
    if not validation["is_valid"]:
        return False, 0, "Validasi terbaru gagal. Paket/kondisi database berubah atau file tidak valid. Unggah ulang untuk melihat rincian."
    try:
        for row in validation["rows"]:
            if mode == "ADD":
                create_package(station_id=station_id, **row["data"], status=PackageStatus.DRAFT, commit=False)
            else:
                package = db.session.get(ChallengePackage, row["existing_id"], populate_existing=True)
                update_package(package, **row["data"], commit=False)
        db.session.commit()
        return True, len(validation["rows"]), None
    except Exception:
        db.session.rollback()
        from flask import current_app
        current_app.logger.exception("Hardware JSON import rolled back")
        return False, 0, "Impor gagal. Seluruh perubahan dibatalkan; tidak ada paket yang disimpan sebagian."
