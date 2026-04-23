import json
import time
import requests

from config import BOT_TOKEN, CHAT_ID
from storage import (
    load,
    save,
    mark_done,
    normalize_text,
    dedupe,
    insert_course_at,
    set_done_status,
    reset_data,
)
from planner import (
    build_daily_batch,
    days_left,
    format_status,
    parse_exam_date,
    quota_for_today,
    remaining_total,
)


BTN_SHOW_ALL = "عرض جميع المقررات"
BTN_SHOW_ALL_WITH_POLLS = "عرض جميع المقررات مع الإستفتاءات"
BTN_TODAY = "مقرر اليوم"
BTN_STATUS = "الحالة"
BTN_REMAINING = "المتبقي"
BTN_MANUAL_ADD = "إضافة يدوية"
BTN_ASK_EXAM_DATE = "متى الامتحان إن شاء الله ؟"
BTN_ASK_TOTAL = "كم مقرر سندرس إن شاء الله ؟"
BTN_EDIT_EXAM_DATE = "تعديل تاريخ الامتحان"
BTN_EDIT_TOTAL = "تعديل عدد المقررات"
BTN_EDIT_PROGRESS = "تعديل الإنجاز"
BTN_RESET = "إعادة تعيين"

RESET_CONFIRM_PHRASE = "بداية جديدة"

API_ROOT = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""


def _allowed_chat(chat_id):
    try:
        return int(chat_id or 0) == int(CHAT_ID or 0)
    except Exception:
        return False


def _post(method, payload):
    if not BOT_TOKEN:
        return None

    try:
        response = requests.post(f"{API_ROOT}/{method}", data=payload, timeout=30)
        return response.json()
    except Exception:
        return None


def _poll_entry_course(entry):
    if isinstance(entry, dict):
        return normalize_text(entry.get("course"))
    return normalize_text(entry)


def _poll_entry_mode(entry):
    if isinstance(entry, dict):
        return normalize_text(entry.get("mode")) or "normal"
    return "normal"


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_query_id}

    if text is not None:
        payload["text"] = text

    payload["show_alert"] = "true" if show_alert else "false"
    _post("answerCallbackQuery", payload)


def main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": BTN_SHOW_ALL}, {"text": BTN_SHOW_ALL_WITH_POLLS}],
            [{"text": BTN_TODAY}, {"text": BTN_STATUS}],
            [{"text": BTN_REMAINING}, {"text": BTN_MANUAL_ADD}],
            [{"text": BTN_ASK_EXAM_DATE}, {"text": BTN_ASK_TOTAL}],
            [{"text": BTN_EDIT_EXAM_DATE}, {"text": BTN_EDIT_TOTAL}],
            [{"text": BTN_EDIT_PROGRESS}, {"text": BTN_RESET}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True,
    }


def send_message(text, keyboard=None):
    if not BOT_TOKEN or not CHAT_ID:
        return None

    if keyboard is None:
        keyboard = main_menu_keyboard()

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


def send_poll(course, mode="normal"):
    if not BOT_TOKEN or not CHAT_ID:
        return None

    result = _post(
        "sendPoll",
        {
            "chat_id": CHAT_ID,
            "question": "هل أنجزت هذا المقرر ؟",
            "options": json.dumps(["نعم ، الحمد لله", "لا للأسف"], ensure_ascii=False),
            "is_anonymous": "false",
            "allows_multiple_answers": "false",
        },
    )

    if result and result.get("ok"):
        poll_id = result["result"]["poll"]["id"]
        data = load()
        data.setdefault("poll_map", {})
        data["poll_map"][poll_id] = {
            "course": normalize_text(course),
            "mode": normalize_text(mode) or "normal",
        }
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

    send_poll(course_n, mode="normal")
    time.sleep(0.5)


def send_edit_status_poll(course):
    course_n = normalize_text(course)
    if not course_n:
        return

    send_message(f"اختر حالة الإنجاز للمقرر التالي:\n{course_n}")
    send_poll(course_n, mode="edit_status")


def send_main_menu():
    send_message("اختر من لوحة الأزرار بالأسفل.", keyboard=main_menu_keyboard())


def ask_exam_date_prompt():
    send_message(
        "متى الامتحان إن شاء الله ؟\n"
        "اكتب التاريخ بأي صيغة مفهومة مثل:\n"
        "15 مايو 2026\n"
        "15 أيلول 2026\n"
        "2026-05-15"
    )


def ask_total_prompt():
    send_message("كم مقرر سندرس إن شاء الله ؟\nاكتب العدد كرقم فقط.")


def edit_exam_date_prompt():
    send_message("أرسل تاريخ الامتحان الجديد.")


def edit_total_prompt():
    send_message("أرسل العدد الكلي الجديد للمقررات.")


def manual_add_name_prompt():
    send_message("أرسل اسم المقرر الذي تريد إضافته يدويًا.")


def manual_add_position_prompt(course_name=None):
    data = load()
    max_position = len(data.get("courses", [])) + 1

    if course_name:
        send_message(
            f"تم استلام اسم المقرر:\n{normalize_text(course_name)}\n\n"
            f"الآن أرسل رقم الترتيب المطلوب بين 1 و {max_position}."
        )
    else:
        send_message(f"أرسل رقم الترتيب المطلوب بين 1 و {max_position}.")


def reset_confirmation_prompt():
    send_message(
        "⚠️ تنبيه مهم\n"
        "سيتم حذف جميع المقررات والمنجز والاستفتاءات النشطة، وسيبدأ البوت من جديد.\n\n"
        f"للتأكيد أرسل العبارة التالية تمامًا:\n{RESET_CONFIRM_PHRASE}"
    )


def send_edit_progress_selection_prompt():
    data = load()
    courses = data.get("courses", [])

    if not courses:
        send_message("لا توجد مقررات حاليًا لتعديل الإنجاز.")
        return

    done = {normalize_text(c) for c in data.get("done", [])}
    lines = ["اختر رقم المقرر الذي تريد تعديل إنجازه:"]

    for index, course in enumerate(courses, start=1):
        course_n = normalize_text(course)
        mark = "✅" if course_n in done else "⬜"
        lines.append(f"{index}. {mark} {course_n}")

    lines.append("")
    lines.append("أرسل الرقم فقط.")

    send_long_message("\n".join(lines))


def send_all_current_courses_with_polls():
    data = load()
    courses = data.get("courses", [])

    if not courses:
        send_message("لا توجد مقررات منشورة حاليًا. سأبقى أتابع القناة.")
        return

    done = dedupe(data.get("done", []))
    active = {
        _poll_entry_course(entry)
        for entry in (data.get("poll_map", {}) or {}).values()
        if _poll_entry_course(entry)
    }

    send_message(
        "لنبدأ بسم الله بمعرفة ما تم إنجازه ، سأرسل لك الآن أسماء المقررات وقم بإعلامي أي المقررات أنجزت ."
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
        f"المتبقي حسب الإجمالي: {remaining_total(load())}"
    )


def send_all_courses_list():
    data = load()
    courses = data.get("courses", [])

    if not courses:
        send_message("لا توجد مقررات منشورة حاليًا.")
        return

    done = {normalize_text(c) for c in data.get("done", [])}
    lines = ["جميع المقررات الحالية:"]

    for index, course in enumerate(courses, start=1):
        course_n = normalize_text(course)
        lines.append(f"{index}. {'✅ ' if course_n in done else ''}{course_n}")

    send_long_message("\n".join(lines))


def send_today_summary():
    data = load()
    batch = build_daily_batch(data)

    if not batch:
        send_message("لا توجد مقررات محددة لليوم الآن.")
        return

    lines = ["مقررات اليوم المقترحة:"]
    for index, course in enumerate(batch, start=1):
        lines.append(f"{index}. {course}")

    send_long_message("\n".join(lines))


def send_remaining_summary():
    data = load()
    send_message(
        f"المتبقي حسب الإجمالي: {remaining_total(data)}\n"
        f"الأيام المتبقية: {days_left(data.get('exam_date'))}\n"
        f"مقررات اليوم المقترحة: {quota_for_today(data)}"
    )


def send_status_summary():
    data = load()
    send_long_message(format_status(data))


def send_initial_courses():
    data = load()

    if not data.get("courses"):
        send_message("لا توجد مقررات منشورة حاليًا. سأبقى أتابع القناة.")
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
            "صيغة التاريخ غير صحيحة. مثال:\n"
            "15 مايو 2026\n"
            "15 أيلول 2026\n"
            "2026-05-15"
        )
        return

    data["exam_date"] = exam_date.isoformat()
    data["phase"] = "running" if data.get("total_courses") else "ask_total"
    save(data)

    send_message(f"تم حفظ تاريخ الامتحان: {data['exam_date']}")

    if data["phase"] == "ask_total":
        ask_total_prompt()
    else:
        send_message("تم تحديث تاريخ الامتحان بنجاح.")


def handle_total_input(text):
    data = load()
    cleaned = normalize_text(text)

    if not cleaned.isdigit():
        send_message("أدخل رقمًا صحيحًا فقط.")
        return

    entered_total = int(cleaned)
    known_courses = len(dedupe(data.get("courses", [])))
    done_count = len(dedupe(data.get("done", [])))
    total = max(entered_total, known_courses, done_count)

    data["total_courses"] = total
    data["phase"] = "running"
    save(data)

    if not data.get("initial_sent"):
        intro_data = load()
        intro_data["initial_sent"] = True
        save(intro_data)

        send_message(
            "لنبدأ بسم الله بمعرفة ما تم إنجازه ، سأرسل لك الآن أسماء المقررات وقم بإعلامي أي المقررات أنجزت ."
        )
        send_initial_courses()
    else:
        send_message(f"تم تحديث العدد الكلي إلى: {total}")

    send_status_summary()


def handle_manual_add_name_input(text):
    data = load()
    course_name = normalize_text(text)

    if not course_name:
        send_message("اسم المقرر لا يمكن أن يكون فارغًا. أرسل اسمًا صحيحًا.")
        return

    existing = {normalize_text(c) for c in data.get("courses", [])}
    if course_name in existing:
        send_message("هذا المقرر موجود مسبقًا في القائمة. أرسل اسمًا آخر أو استخدم عرض جميع المقررات.")
        return

    data["pending_manual_course"] = course_name
    data["phase"] = "ask_manual_course_position"
    save(data)

    manual_add_position_prompt(course_name)


def handle_manual_add_position_input(text):
    data = load()
    cleaned = normalize_text(text)
    course_name = normalize_text(data.get("pending_manual_course"))

    if not course_name:
        data["phase"] = "running"
        data["pending_manual_course"] = None
        save(data)
        send_message("لم أجد اسم المقرر المراد إضافته. ابدأ العملية من جديد عبر زر إضافة يدوية.")
        return

    if not cleaned.isdigit():
        send_message("أرسل رقم ترتيب صحيح فقط.")
        manual_add_position_prompt(course_name)
        return

    position = int(cleaned)

    try:
        insert_course_at(data, course_name, position)
    except ValueError as exc:
        send_message(str(exc))
        return

    current_total = int(data.get("total_courses") or 0)
    known_courses = len(dedupe(data.get("courses", [])))
    if current_total < known_courses:
        data["total_courses"] = known_courses

    data["phase"] = "running"
    data["pending_manual_course"] = None
    save(data)

    send_message(
        f"✅ تم إضافة المقرر بنجاح:\n{course_name}\n"
        f"📍 ترتيبه الحالي: {position}"
    )
    send_all_courses_list()


def handle_edit_progress_selection_input(text):
    data = load()
    cleaned = normalize_text(text)

    if not cleaned.isdigit():
        send_message("أرسل رقم المقرر فقط كما هو ظاهر في القائمة.")
        send_edit_progress_selection_prompt()
        return

    index = int(cleaned)
    courses = data.get("courses", [])

    if index < 1 or index > len(courses):
        send_message("الرقم خارج نطاق المقررات الحالية. حاول مرة أخرى.")
        send_edit_progress_selection_prompt()
        return

    course = normalize_text(courses[index - 1])
    done = {normalize_text(c) for c in data.get("done", [])}
    current_state = "✅ منجز" if course in done else "⬜ غير منجز"

    data["phase"] = "running"
    save(data)

    send_message(f"المقرر المختار:\n{course}\nالحالة الحالية: {current_state}")
    send_edit_status_poll(course)


def perform_reset():
    current = load()
    clean = reset_data(current)
    save(clean)

    send_message("✅ تمّت إعادة التعيين بنجاح. سنبدأ من جديد الآن.")
    ask_exam_date_prompt()


def handle_poll_answer(update):
    poll_answer = update.get("poll_answer", {})
    poll_id = poll_answer.get("poll_id")
    option_ids = poll_answer.get("option_ids", [])

    if not poll_id:
        return

    data = load()
    entry = (data.get("poll_map", {}) or {}).get(poll_id)

    if not entry:
        return

    course = _poll_entry_course(entry)
    mode = _poll_entry_mode(entry)

    if not course:
        data.get("poll_map", {}).pop(poll_id, None)
        save(data)
        return

    if mode == "edit_status":
        if 0 in option_ids:
            set_done_status(data, course, True)
            send_message(f"✅ تم تعديل الإنجاز للمقرر إلى: منجز\n{course}")
        else:
            set_done_status(data, course, False)
            send_message(f"↩️ تم تعديل الإنجاز للمقرر إلى: غير منجز\n{course}")
    else:
        if 0 in option_ids:
            mark_done(data, course)
            send_message(f"✅ تم إنجاز المقرر:\n{course}")
        else:
            send_message(f"⏳ سيبقى هذا المقرر في الجدولة:\n{course}")

    data.get("poll_map", {}).pop(poll_id, None)
    save(data)

    send_message(f"المتبقي الآن: {remaining_total(load())}")


def _handle_action(action_text):
    data = load()

    if action_text == BTN_SHOW_ALL:
        send_all_courses_list()
        return True

    if action_text == BTN_SHOW_ALL_WITH_POLLS:
        send_all_current_courses_with_polls()
        return True

    if action_text == BTN_TODAY:
        send_today_summary()
        return True

    if action_text == BTN_STATUS:
        send_status_summary()
        return True

    if action_text == BTN_REMAINING:
        send_remaining_summary()
        return True

    if action_text == BTN_MANUAL_ADD:
        data["phase"] = "ask_manual_course_name"
        data["pending_manual_course"] = None
        save(data)
        manual_add_name_prompt()
        return True

    if action_text == BTN_ASK_EXAM_DATE:
        data["phase"] = "ask_exam_date"
        save(data)
        ask_exam_date_prompt()
        return True

    if action_text == BTN_ASK_TOTAL:
        data["phase"] = "ask_total"
        save(data)
        ask_total_prompt()
        return True

    if action_text == BTN_EDIT_EXAM_DATE:
        data["phase"] = "edit_exam_date"
        save(data)
        edit_exam_date_prompt()
        return True

    if action_text == BTN_EDIT_TOTAL:
        data["phase"] = "edit_total"
        save(data)
        edit_total_prompt()
        return True

    if action_text == BTN_EDIT_PROGRESS:
        data["phase"] = "edit_progress_select"
        save(data)
        send_edit_progress_selection_prompt()
        return True

    if action_text == BTN_RESET:
        data["phase"] = "confirm_reset"
        data["pending_manual_course"] = None
        save(data)
        reset_confirmation_prompt()
        return True

    return False


def handle_callback_query(update):
    """
    إبقاء دعم callback_query فقط للتوافق مع أي رسائل inline قديمة
    موجودة في المحادثة من الإصدارات السابقة.
    """
    callback_query = update.get("callback_query", {})
    callback_id = callback_query.get("id")
    data_value = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id", 0)

    if not _allowed_chat(chat_id):
        return

    answer_callback_query(callback_id)

    legacy_map = {
        "menu": None,
        "show_all_list": BTN_SHOW_ALL,
        "show_all_with_polls": BTN_SHOW_ALL_WITH_POLLS,
        "show_today": BTN_TODAY,
        "show_status": BTN_STATUS,
        "show_remaining": BTN_REMAINING,
        "ask_exam_date": BTN_ASK_EXAM_DATE,
        "ask_total": BTN_ASK_TOTAL,
        "edit_exam_date": BTN_EDIT_EXAM_DATE,
        "edit_total": BTN_EDIT_TOTAL,
        "manual_add": BTN_MANUAL_ADD,
        "edit_progress": BTN_EDIT_PROGRESS,
        "reset_all": BTN_RESET,
    }

    if data_value == "menu":
        send_main_menu()
        return

    action_text = legacy_map.get(data_value)
    if action_text:
        _handle_action(action_text)


def handle_text_message(text, chat_id=None):
    if chat_id is not None and not _allowed_chat(chat_id):
        return

    cleaned = normalize_text((text or "").strip())
    lower_cleaned = cleaned.lower()

    data = load()
    phase = data.get("phase", "ask_exam_date")

    if lower_cleaned in {"/start", "start", "/menu", "menu"}:
        if phase in {"ask_manual_course_name", "ask_manual_course_position", "edit_progress_select", "confirm_reset"}:
            data["phase"] = "running"
            data["pending_manual_course"] = None
            save(data)

        send_main_menu()
        return

    if phase == "confirm_reset" and cleaned == RESET_CONFIRM_PHRASE:
        perform_reset()
        return

    action_aliases = {
        BTN_SHOW_ALL: {BTN_SHOW_ALL, "/list", "list", "جميع المقررات"},
        BTN_SHOW_ALL_WITH_POLLS: {
            BTN_SHOW_ALL_WITH_POLLS,
            "عرض جميع المقررات مع الاستفتاءات",
            "/all",
            "all",
        },
        BTN_TODAY: {BTN_TODAY, "/today", "today", "الخطة"},
        BTN_STATUS: {BTN_STATUS, "/status", "status"},
        BTN_REMAINING: {BTN_REMAINING, "/remaining", "remaining", "كم باقي"},
        BTN_MANUAL_ADD: {BTN_MANUAL_ADD, "اضافة يدوية", "/manualadd", "manualadd"},
        BTN_ASK_EXAM_DATE: {BTN_ASK_EXAM_DATE, "/setdate", "setdate"},
        BTN_ASK_TOTAL: {BTN_ASK_TOTAL, "/settotal", "settotal"},
        BTN_EDIT_EXAM_DATE: {BTN_EDIT_EXAM_DATE},
        BTN_EDIT_TOTAL: {BTN_EDIT_TOTAL},
        BTN_EDIT_PROGRESS: {BTN_EDIT_PROGRESS, "تعديل الانجاز", "/editprogress", "editprogress"},
        BTN_RESET: {BTN_RESET},
    }

    for action_text, variants in action_aliases.items():
        normalized_variants = {normalize_text(v).lower() for v in variants}
        if cleaned in variants or lower_cleaned in normalized_variants:
            if phase == "confirm_reset":
                data["phase"] = "running"
                save(data)

            _handle_action(action_text)
            return

    if phase == "confirm_reset":
        send_message(
            f"لم يتم تنفيذ إعادة التعيين بعد. للتأكيد أرسل العبارة التالية تمامًا:\n{RESET_CONFIRM_PHRASE}"
        )
        return

    if phase in {"ask_exam_date", "edit_exam_date"}:
        handle_exam_date_input(cleaned)
        return

    if phase in {"ask_total", "edit_total"}:
        handle_total_input(cleaned)
        return

    if phase == "ask_manual_course_name":
        handle_manual_add_name_input(cleaned)
        return

    if phase == "ask_manual_course_position":
        handle_manual_add_position_input(cleaned)
        return

    if phase == "edit_progress_select":
        handle_edit_progress_selection_input(cleaned)
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

    if phase == "ask_manual_course_name":
        manual_add_name_prompt()
        return

    if phase == "ask_manual_course_position":
        manual_add_position_prompt(data.get("pending_manual_course"))
        return

    if phase == "edit_progress_select":
        send_edit_progress_selection_prompt()
        return

    if phase == "confirm_reset":
        reset_confirmation_prompt()
        return

    send_main_menu()


def send_daily_batch():
    data = load()
    batch = build_daily_batch(data)

    if not batch:
        if remaining_total(data) == 0:
            send_message("🎉 تم إنهاء جميع المقررات المسجلة.")
        return

    send_message("📅 مقررات اليوم:")

    for course in batch:
        send_course_with_poll(course)
