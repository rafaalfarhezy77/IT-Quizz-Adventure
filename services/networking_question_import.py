"""Networking-specific import structure and stage contract, independent of member rotation."""
STAGES = {
    1: {"name": "Signal Check", "type": "multiple_choice", "count": 10, "points": 3, "offset": 0},
    2: {"name": "True or Trap", "type": "true_false", "count": 10, "points": 4, "offset": 10},
    3: {"name": "Case Signal", "type": "short_text", "count": 5, "points": 6, "offset": 20},
}


def _legacy_cases(rows):
    result = []
    for row in rows:
        if isinstance(row, dict):
            row = dict(row)
            text = row.get("text", "")
            if row.get("stage") == 3 and not row.get("case_study") and isinstance(text, str) and text.startswith("(Tema:") and ". " in text:
                scenario, question = text.rsplit(". ", 1)
                row["case_study"], row["text"] = scenario + ".", question
        result.append(row)
    return result


def flatten_networking_set(value):
    """Accept canonical stage groups and compatible legacy flat arrays."""
    errors = []
    if isinstance(value, list):
        return _legacy_cases(value), errors
    if not isinstance(value, dict):
        return [], ["Set Networking harus berisi objek stages atau array 25 soal."]
    if "case_study" in value:
        errors.append("Networking memakai studi kasus per soal, bukan satu studi kasus per set seperti Software Engineering.")
    if "stages" not in value:
        questions = value.get("questions")
        return (_legacy_cases(questions) if isinstance(questions, list) else []), errors + ([] if isinstance(questions, list) else ["Set Networking wajib memuat stages 1, 2, 3."])
    stages = value["stages"]
    if not isinstance(stages, dict):
        return [], errors + ["stages harus berupa objek dengan kunci 1, 2, 3."]
    if set(stages) != {"1", "2", "3"}:
        errors.append("stages wajib memuat tepat tiga tahap dengan kunci 1, 2, 3.")
    questions = []
    for stage, spec in STAGES.items():
        rows = stages.get(str(stage))
        if not isinstance(rows, list):
            errors.append(f"Tahap {stage} ({spec['name']}) wajib berupa array soal.")
            continue
        if len(rows) != spec["count"]:
            errors.append(f"Tahap {stage} ({spec['name']}) wajib berisi {spec['count']} soal.")
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                questions.append(row)
                continue
            q = dict(row)
            if "stage" in q and q["stage"] != stage:
                errors.append(f"Soal {index} berada pada grup tahap {stage}, tetapi stage bernilai {q['stage']}.")
            q.setdefault("stage", stage)
            q.setdefault("question_type", spec["type"])
            q.setdefault("weight", spec["points"])
            q.setdefault("order_number", spec["offset"] + index)
            questions.append(q)
    return questions, errors
