"""Pure scoring primitives shared by competition and practice."""


def answer_points(selected, correct, weight):
    matched = bool(selected) and selected.strip().upper() == correct.strip().upper()
    return matched, float(weight) if matched else 0.0


def time_bonus(remaining, rate, timeout=False):
    return 0.0 if timeout else round(max(0, remaining) * rate, 2)
