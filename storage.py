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
        "pending_manual_course": None,
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
    base = default_data()
    base.update(data or {})
    base["courses"] = dedupe(base.get("courses", []))
    base["done"] = dedupe(base.get("done", []))

    if not isinstance(base.get("poll_map"), dict):
        base["poll_map"] = {}

    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)

    os.replace(tmp, FILE)


def mark_done(data, course):
    course = normalize_text(course)

    if course and course not in data["done"]:
        data["done"].append(course)

    data["done"] = dedupe(data["done"])
    return data


def set_done_status(data, course, is_done):
    course = normalize_text(course)
    done = dedupe(data.get("done", []))

    if not course:
        data["done"] = done
        return data

    if is_done:
        if course not in done:
            done.append(course)
    else:
        done = [item for item in done if normalize_text(item) != course]

    data["done"] = dedupe(done)
    return data


def insert_course_at(data, course, position):
    course = normalize_text(course)
    courses = dedupe(data.get("courses", []))

    if not course:
        raise ValueError("اسم المقرر فارغ.")

    max_position = len(courses) + 1
    if position < 1 or position > max_position:
        raise ValueError(f"رقم الترتيب يجب أن يكون بين 1 و {max_position}.")

    if course in courses:
        raise ValueError("هذا المقرر موجود مسبقًا في القائمة.")

    courses.insert(position - 1, course)
    data["courses"] = courses
    return data


def reset_data(current=None):
    """
    إعادة ضبط كاملة مع الإبقاء على offset فقط
    حتى لا يعيد البوت معالجة تحديثات قديمة من Telegram.
    """
    clean = default_data()

    if current:
        clean["offset"] = int(current.get("offset", 0) or 0)

    return clean
