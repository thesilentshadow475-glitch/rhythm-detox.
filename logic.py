"""Pure helpers for the Rhythm Detox agent (no network, easy to test)."""
import json, re

TYPES = {"focus", "offline", "winddown", "free"}


def to_min(t):
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


def window(profile):
    w, s = to_min(profile["wake"]), to_min(profile["sleep"])
    if s <= w:
        s += 1440
    return w, s


def normalize(profile, plan):
    w, _ = window(profile)
    out = []
    for b in plan.get("blocks", []):
        a, e = to_min(b["start"]), to_min(b["end"])
        if a < w:
            a += 1440
        if e <= a:
            e += 1440
        out.append({**b, "a": a, "e": e})
    return sorted(out, key=lambda x: x["a"])


def validate_plan(profile, plan):
    """Return a list of problems; an empty list means the plan is valid."""
    try:
        blocks = normalize(profile, plan)
    except Exception:
        return ["Every block needs 'start' and 'end' as HH:MM strings."]
    w, s = window(profile)
    ws, we = to_min(profile["ws"]), to_min(profile["we"])
    issues = []
    if not 4 <= len(blocks) <= 8:
        issues.append("Use between 4 and 8 blocks.")
    prev = w
    for b in blocks:
        name = b.get("label", "block")
        if b.get("type") not in TYPES:
            issues.append(f"{name}: type must be one of {sorted(TYPES)}.")
        if b["a"] < w or b["e"] > s:
            issues.append(f"{name}: must sit between wake-up and bedtime.")
        if b["a"] < prev:
            issues.append(f"{name}: overlaps the previous block.")
        prev = max(prev, b["e"])
        if b.get("type") == "focus" and not (ws <= b["a"] and b["e"] <= we):
            issues.append(f"{name}: focus blocks must be inside work/study hours.")
    wd = [b for b in blocks if b.get("type") == "winddown"]
    if not wd or wd[-1]["e"] != s:
        issues.append("A 'winddown' block must end exactly at bedtime.")
    return issues


def rhythm_score(profile, plan):
    """Deterministic projected score (0-100) so the number is not guessed by the model."""
    try:
        blocks = normalize(profile, plan)
    except Exception:
        return 0
    dur = lambda t: sum(b["e"] - b["a"] for b in blocks if b.get("type") == t)
    base = max(20, 90 - float(profile.get("hrs", 6)) * 4)
    bonus = min(10, dur("offline") / 12) + min(10, dur("focus") / 30) + (5 if dur("winddown") >= 45 else 0)
    return int(max(0, min(100, round(base + bonus))))


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("No JSON object found in the model reply.")
    return json.loads(m.group(0))
