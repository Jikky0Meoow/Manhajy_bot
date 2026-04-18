import json
import os


FILE = "data.json"


def default_data():
    return {
        "phase": "ask_exam_date",
        "prompt_sent": False,
        "initial_sent": False,
        "exam_date": None,
        "total_courses": None,
        "courses": [],
        "done": [],
        "poll_map": {},
        "last_daily_date": None,
        "offset": 0,
        "last_message_id": 0,
    }


def normalize_text(text):
    return " ".join((text or "").split()).strip()


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        item = normalize_text(item)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def load():
    if not os.path.exists(FILE):
        return default_data()

    try:
        with open(FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default_data()

    base = default_data()
    base.update(data)
    base["courses"] = dedupe(base.get("courses", []))
    base["done"] = dedupe(base.get("done", []))
    if not isinstance(base.get("poll_map"), dict):
        base["poll_map"] = {}
    return base


def save(data):
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FILE)


def mark_done(data, course):
    course = normalize_text(course)
    if course and course not in data["done"]:
        data["done"].append(course)
    data["done"] = dedupe(data["done"])
    return data
