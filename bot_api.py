import json
import time
import requests

from config import BOT_TOKEN, CHAT_ID
from storage import load, save, mark_done, normalize_text, dedupe
from planner import (
    build_daily_batch,
    days_left,
    format_status,
    parse_exam_date,
    quota_for_today,
    remaining_total,
    today_amman,
)


API_ROOT = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""


def _post(method, payload):
    if not BOT_TOKEN:
        return None

    try:
        response = requests.post(f"{API_ROOT}/{method}", data=payload, timeout=30)
        return response.json()
    except Exception:
        return None


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    payload = {
        "callback_query_id": callback_query_id,
    }

    if text is not None:
        payload["text"] = text

    payload["show_alert"] = "true" if show_alert else "false"
    _post("answerCallbackQuery", payload)


def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "متى الامتحان إن شاء الله ؟", "callback_data": "ask_exam_date"},
                {"text": "كم مقرر سندرس إن شاء الله ؟", "callback_data": "ask_total"},
            ],
            [
                {"text": "إرسال جميع المقررات مع الاستفتاءات", "callback_data": "show_all_with_polls"},
                {"text": "عرض جميع المقررات", "callback_data": "show_all_list"},
            ],
            [
                {"text": "مقررات اليوم", "callback_data": "show_today"},
                {"text": "المتبقي", "callback_data": "show_remaining"},
            ],
            [
                {"text": "الحالة", "callback_data": "show_status"},
                {"text": "القائمة الرئيسية", "callback_data": "menu"},
            ],
            [
                {"text": "تعديل تاريخ الامتحان", "callback_data": "edit_exam_date"},
                {"text": "تعديل عدد المقررات", "callback_data": "edit_total"},
            ],
        ]
    }


def send_message(text, keyboard=None):
    if not BOT_TOKEN or not CHAT_ID:
        return None

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
    }

    if keyboard is not None:
        payload["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)

    return _post("sendMessage", payload)


def send_long_message(text, keyboard=None):
    text = text or ""
    limit = 3500

    if len(text) <= limit:
        send_message(text, keyboard=keyboard)
        return

    parts = []
    current = ""

    for paragraph in text.split("\n"):
        if len(current) + len(paragraph) + 1 > limit:
            parts.append(current.rstrip())
            current = paragraph + "\n"
        else:
            current += paragraph + "\n"

    if current.strip():
        parts.append(current.rstrip())

    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            send_message(part, keyboard=keyboard)
        else:
            send_message(part)


def send_poll(course):
    if not BOT_TOKEN or not CHAT_ID:
        return None

    result = _post("sendPoll", {
        "chat_id": CHAT_ID,
        "question": "هل أنجزت المقرر ؟",
        "options": json.dumps(["نعم ، الحمد لله", "لا للأسف"], ensure_ascii=False),
        "is_anonymous": "false",
        "allows_multiple_answers": "false",
    })

    if result and result.get("ok"):
        poll_id = result["result"]["poll"]["id"]
        data = load()
        data.setdefault("poll_map", {})
        data["poll_map"][poll_id] = normalize_text(course)
        save(data)
        return poll_id

    return None


def send_course_with_poll(course, prefix=None):
    course_n = normalize_text(course)
    if not course_n:
        return

    if prefix:
        send_message(f"{prefix}\n{course_n}")
    else:
        send_message(f"📚 {course_n}")

    send_poll(course_n)
    time.sleep(0.5)


def send_main_menu():
    send_message(
        "اختر ما تريد من الأزرار التالية:",
        keyboard=main_menu_keyboard()
    )


def ask_exam_date_prompt():
    send_message(
        "متى الامتحان إن شاء الله ؟\n"
        "اكتب التاريخ بأي صيغة مفهومة مثل:\n"
        "15 مايو 2026\n"
        "15 أيلول 2026\n"
        "2026-05-15",
        keyboard=main_menu_keyboard()
    )


def ask_total_prompt():
    send_message(
        "كم مقرر سندرس إن شاء الله ؟\n"
        "اكتب العدد كرقم فقط.",
        keyboard=main_menu_keyboard()
    )


def edit_exam_date_prompt():
    send_message(
        "أرسل تاريخ الامتحان الجديد.",
        keyboard=main_menu_keyboard()
    )


def edit_total_prompt():
    send_message(
        "أرسل العدد الكلي الجديد للمقررات.",
        keyboard=main_menu_keyboard()
    )


def send_all_current_courses_with_polls():
    data = load()
    courses = data.get("courses", [])

    if not courses:
        send_message(
            "لا توجد مقررات منشورة حاليًا. سأبقى أتابع القناة.",
            keyboard=main_menu_keyboard()
        )
        return

    done = dedupe(data.get("done", []))
    active = {normalize_text(course) for course in (data.get("poll_map", {}) or {}).values()}

    send_message(
        "لنبدأ بسم الله بمعرفة ما تم إنجازه ، سأرسل لك الآن أسماء المقررات وقم بإعلامي أي المقررات أنجزت .",
        keyboard=main_menu_keyboard()
    )

    sent_count = 0

    for course in courses:
        course_n = normalize_text(course)
        if not course_n:
            continue

        if course_n in done:
            send_message(f"✅ {course_n} (منجز)")
            continue

        if course_n in active:
            continue

        send_course_with_poll(course_n)
        sent_count += 1

    send_message(
        f"تم إرسال المقررات الحالية.\n"
        f"المقررات التي أرسلت الآن: {sent_count}\n"
        f"المنجز حاليًا: {len(done)}\n"
        f"المتبقي حسب الإجمالي: {remaining_total(load())}",
        keyboard=main_menu_keyboard()
    )


def send_all_courses_list():
    data = load()
    courses = data.get("courses", [])

    if not courses:
        send_message("لا توجد مقررات منشورة حاليًا.", keyboard=main_menu_keyboard())
        return

    done = {normalize_text(c) for c in data.get("done", [])}
    lines = ["جميع المقررات الحالية:"]

    for index, course in enumerate(courses, start=1):
        course_n = normalize_text(course)
        if course_n in done:
            lines.append(f"{index}. ✅ {course_n}")
        else:
            lines.append(f"{index}. {course_n}")

    send_long_message("\n".join(lines), keyboard=main_menu_keyboard())


def send_today_summary():
    data = load()
    batch = build_daily_batch(data)

    if not batch:
        send_message(
            "لا توجد مقررات محددة لليوم الآن.",
            keyboard=main_menu_keyboard()
        )
        return

    lines = ["مقررات اليوم المقترحة:"]
    for index, course in enumerate(batch, start=1):
        lines.append(f"{index}. {course}")

    send_long_message("\n".join(lines), keyboard=main_menu_keyboard())


def send_remaining_summary():
    data = load()
    send_message(
        f"المتبقي حسب الإجمالي: {remaining_total(data)}\n"
        f"الأيام المتبقية: {days_left(data.get('exam_date'))}\n"
        f"مقررات اليوم المقترحة: {quota_for_today(data)}",
        keyboard=main_menu_keyboard()
    )


def send_status_summary():
    data = load()
    send_long_message(format_status(data), keyboard=main_menu_keyboard())


def send_initial_courses():
    data = load()
    if not data.get("courses"):
        send_message(
            "لا توجد مقررات منشورة حاليًا. سأبقى أتابع القناة.",
            keyboard=main_menu_keyboard()
        )
        return

    if not data.get("initial_sent"):
        data["initial_sent"] = True
        save(data)

    send_all_current_courses_with_polls()


def handle_exam_date_input(text):
    data = load()

    try:
        exam_date = parse_exam_date(text)
    except Exception:
        send_message(
            "صيغة التاريخ غير صحيحة. مثال:\n15 مايو 2026\n15 أيلول 2026\n2026-05-15",
            keyboard=main_menu_keyboard()
        )
        return

    data["exam_date"] = exam_date.isoformat()

    if data.get("total_courses"):
        data["phase"] = "running"
    else:
        data["phase"] = "ask_total"

    save(data)

    send_message(
        f"تم حفظ تاريخ الامتحان: {data['exam_date']}",
        keyboard=main_menu_keyboard()
    )

    if data["phase"] == "ask_total":
        ask_total_prompt()
    else:
        send_message(
            "تم تحديث تاريخ الامتحان بنجاح.",
            keyboard=main_menu_keyboard()
        )


def handle_total_input(text):
    data = load()
    cleaned = normalize_text(text)

    if not cleaned.isdigit():
        send_message(
            "أدخل رقمًا صحيحًا فقط.",
            keyboard=main_menu_keyboard()
        )
        return

    entered_total = int(cleaned)
    known_courses = len(dedupe(data.get("courses", [])))
    done_count = len(dedupe(data.get("done", [])))

    total = entered_total
    if total < known_courses:
        total = known_courses

    if total < done_count:
        total = done_count

    data["total_courses"] = total
    data["phase"] = "running"
    save(data)

    if not data.get("initial_sent"):
        intro_data = load()
        intro_data["initial_sent"] = True
        save(intro_data)

        send_message(
            "لنبدأ بسم الله بمعرفة ما تم إنجازه ، سأرسل لك الآن أسماء المقررات وقم بإعلامي أي المقررات أنجزت .",
            keyboard=main_menu_keyboard()
        )

        send_initial_courses()
    else:
        send_message(
            f"تم تحديث العدد الكلي إلى: {total}",
            keyboard=main_menu_keyboard()
        )

    send_status_summary()


def handle_poll_answer(update):
    poll_answer = update.get("poll_answer", {})
    poll_id = poll_answer.get("poll_id")
    option_ids = poll_answer.get("option_ids", [])

    if not poll_id:
        return

    data = load()
    course = (data.get("poll_map", {}) or {}).get(poll_id)

    if not course:
        return

    if 0 in option_ids:
        mark_done(data, course)
        send_message(f"✅ تم إنجاز المقرر:\n{course}")
    else:
        send_message(f"⏳ سيبقى هذا المقرر في الجدولة:\n{course}")

    data.get("poll_map", {}).pop(poll_id, None)
    save(data)

    send_message(
        f"المتبقي الآن: {remaining_total(load())}",
        keyboard=main_menu_keyboard()
    )


def handle_callback_query(update):
    callback_query = update.get("callback_query", {})
    callback_id = callback_query.get("id")
    data_value = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id", 0)

    if int(chat_id or 0) != CHAT_ID:
        return

    answer_callback_query(callback_id)

    data = load()

    if data_value == "menu":
        send_main_menu()
        return

    if data_value == "ask_exam_date":
        data["phase"] = "ask_exam_date"
        save(data)
        ask_exam_date_prompt()
        return

    if data_value == "ask_total":
        data["phase"] = "ask_total"
        save(data)
        ask_total_prompt()
        return

    if data_value == "edit_exam_date":
        data["phase"] = "edit_exam_date"
        save(data)
        edit_exam_date_prompt()
        return

    if data_value == "edit_total":
        data["phase"] = "edit_total"
        save(data)
        edit_total_prompt()
        return

    if data_value == "show_all_with_polls":
        send_all_current_courses_with_polls()
        return

    if data_value == "show_all_list":
        send_all_courses_list()
        return

    if data_value == "show_today":
        send_today_summary()
        return

    if data_value == "show_remaining":
        send_remaining_summary()
        return

    if data_value == "show_status":
        send_status_summary()
        return


def handle_text_message(text):
    data = load()
    phase = data.get("phase", "ask_exam_date")
    cleaned = (text or "").strip()
    lower_cleaned = normalize_text(cleaned).lower()

    if lower_cleaned in {"/start", "start"}:
        send_main_menu()
        return

    if lower_cleaned in {"/menu", "menu", "القائمة"}:
        send_main_menu()
        return

    if phase in {"ask_exam_date", "edit_exam_date"}:
        handle_exam_date_input(cleaned)
        return

    if phase in {"ask_total", "edit_total"}:
        handle_total_input(cleaned)
        return

    if lower_cleaned in {"/all", "all", "جميع المقررات"}:
        send_all_current_courses_with_polls()
        return

    if lower_cleaned in {"/list", "list", "عرض جميع المقررات"}:
        send_all_courses_list()
        return

    if lower_cleaned in {"/today", "today", "مقرر اليوم", "الخطة"}:
        send_today_summary()
        return

    if lower_cleaned in {"/remaining", "remaining", "المتبقي", "كم باقي"}:
        send_remaining_summary()
        return

    if lower_cleaned in {"/status", "status", "الحالة"}:
        send_status_summary()
        return

    if lower_cleaned in {"/setdate", "setdate"}:
        ask_exam_date_prompt()
        return

    if lower_cleaned in {"/settotal", "settotal"}:
        ask_total_prompt()
        return

    send_main_menu()


def send_startup_prompt():
    data = load()
    phase = data.get("phase", "ask_exam_date")

    if phase == "ask_exam_date" and not data.get("prompt_sent"):
        data["prompt_sent"] = True
        save(data)
        ask_exam_date_prompt()
        return

    if phase == "ask_total":
        ask_total_prompt()
        return

    if phase == "edit_exam_date":
        edit_exam_date_prompt()
        return

    if phase == "edit_total":
        edit_total_prompt()
        return

    if phase == "running":
        send_main_menu()
        return


def send_daily_batch():
    data = load()
    batch = build_daily_batch(data)

    if not batch:
        if remaining_total(data) == 0:
            send_message("🎉 تم إنهاء جميع المقررات المسجلة.", keyboard=main_menu_keyboard())
        return

    send_message("📅 مقررات اليوم:", keyboard=main_menu_keyboard())

    for course in batch:
        send_course_with_poll(course)
