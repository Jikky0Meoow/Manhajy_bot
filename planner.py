import math
import re
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    AMMAN = ZoneInfo("Asia/Amman")
except Exception:
    AMMAN = None


DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


MONTH_ALIASES = {
    "يناير": 1,
    "jan": 1,
    "january": 1,
    "كانون الثاني": 1,

    "فبراير": 2,
    "feb": 2,
    "february": 2,
    "شباط": 2,

    "مارس": 3,
    "mar": 3,
    "march": 3,
    "اذار": 3,
    "آذار": 3,

    "ابريل": 4,
    "أبريل": 4,
    "apr": 4,
    "april": 4,
    "نيسان": 4,

    "مايو": 5,
    "may": 5,
    "ايار": 5,
    "أيار": 5,

    "يونيو": 6,
    "june": 6,
    "jun": 6,
    "حزيران": 6,

    "يوليو": 7,
    "july": 7,
    "jul": 7,
    "تموز": 7,

    "اغسطس": 8,
    "أغسطس": 8,
    "august": 8,
    "aug": 8,
    "آب": 8,
    "اب": 8,

    "سبتمبر": 9,
    "september": 9,
    "sep": 9,
    "أيلول": 9,
    "ايلول": 9,

    "اكتوبر": 10,
    "أكتوبر": 10,
    "october": 10,
    "oct": 10,
    "تشرين الاول": 10,
    "تشرين الأول": 10,

    "نوفمبر": 11,
    "november": 11,
    "nov": 11,
    "تشرين الثاني": 11,

    "ديسمبر": 12,
    "december": 12,
    "dec": 12,
    "كانون الاول": 12,
    "كانون الأول": 12,
}


def normalize_text(text):
    return " ".join((text or "").split()).strip()


def normalize_digits(text):
    return (text or "").translate(DIGIT_TRANSLATION)


def now_amman():
    if AMMAN:
        return datetime.now(AMMAN)
    return datetime.utcnow()


def today_amman():
    return now_amman().date()


def parse_exam_date(raw):
    raw = normalize_text(normalize_digits(raw)).lower()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    match = re.match(r"^(\d{1,2})\s+(.+?)\s+(\d{4})$", raw)
    if not match:
        raise ValueError("صيغة التاريخ غير صحيحة")

    day = int(match.group(1))
    month_text = normalize_text(match.group(2)).lower()
    year = int(match.group(3))

    month = MONTH_ALIASES.get(month_text)
    if not month:
        raise ValueError("اسم الشهر غير معروف")

    return date(year, month, day)


def days_left(exam_date_str, on_date=None):
    if not exam_date_str:
        return 0

    on_date = on_date or today_amman()
    exam_date = date.fromisoformat(exam_date_str)
    return max(0, (exam_date - on_date).days)


def done_courses_set(data):
    return {normalize_text(c) for c in data.get("done", [])}


def active_poll_courses(data):
    poll_map = data.get("poll_map", {}) or {}
    out = set()

    for entry in poll_map.values():
        if isinstance(entry, dict):
            course = normalize_text(entry.get("course"))
        else:
            course = normalize_text(entry)

        if course:
            out.add(course)

    return out


def remaining_courses(data):
    done = done_courses_set(data)
    active = active_poll_courses(data)

    out = []
    for course in data.get("courses", []):
        course_n = normalize_text(course)
        if course_n and course_n not in done and course_n not in active:
            out.append(course_n)

    return out


def remaining_total(data):
    total = int(data.get("total_courses") or 0)
    done_count = len(done_courses_set(data))
    return max(0, total - done_count)


def quota_for_today(data, on_date=None):
    on_date = on_date or today_amman()
    days = days_left(data.get("exam_date"), on_date)
    if days <= 0:
        return 0

    remaining = remaining_total(data)
    if remaining <= 0:
        return 0

    return max(1, math.ceil(remaining / days))


def build_daily_batch(data, on_date=None):
    on_date = on_date or today_amman()
    quota = quota_for_today(data, on_date)

    if quota <= 0:
        return []

    available = remaining_courses(data)
    return available[:quota]


def build_schedule_map(data, start_day=None):
    start_day = start_day or today_amman()

    exam_date_str = data.get("exam_date")
    if not exam_date_str:
        return {}

    exam = date.fromisoformat(exam_date_str)
    days = max(0, (exam - start_day).days)
    if days <= 0:
        return {}

    remaining = remaining_courses(data)
    if not remaining:
        return {}

    schedule = {}
    index = 0

    for i in range(days):
        current_day = start_day + timedelta(days=i)

        days_left_now = max(1, days - i)
        quota = max(1, math.ceil(len(remaining[index:]) / days_left_now))

        schedule[current_day.isoformat()] = remaining[index:index + quota]
        index += quota

        if index >= len(remaining):
            for j in range(i + 1, days):
                future_day = start_day + timedelta(days=j)
                schedule[future_day.isoformat()] = []
            break

    return schedule


def schedule_for_day(data, day_date=None):
    day_date = day_date or today_amman()
    schedule = build_schedule_map(data, day_date)
    return schedule.get(day_date.isoformat(), [])


def format_status(data):
    exam = data.get("exam_date") or "غير محدد"
    total = int(data.get("total_courses") or 0)
    done_count = len(done_courses_set(data))
    active_count = len(active_poll_courses(data))
    remaining = remaining_total(data)
    days = days_left(data.get("exam_date"))
    quota = quota_for_today(data)
    current_known = len(data.get("courses", []))

    return (
        f"تاريخ الامتحان: {exam}\n"
        f"الإجمالي الذي أدخلته: {total}\n"
        f"المقررات المنشورة حاليًا: {current_known}\n"
        f"المنجز: {done_count}\n"
        f"الاستفتاءات النشطة: {active_count}\n"
        f"المتبقي حسب الإجمالي: {remaining}\n"
        f"الأيام المتبقية: {days}\n"
        f"مقررات اليوم المقترحة: {quota}"
    )
