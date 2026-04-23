from telethon import events

from parser import extract_courses
from storage import load, save, dedupe, normalize_text
from bot_api import send_message, main_menu_keyboard


def register_collector(client, channel):
    @client.on(events.NewMessage(chats=channel))
    async def handler(event):
        text = event.raw_text or ""
        courses = extract_courses(text)

        if not courses:
            return

        data = load()
        before = set(dedupe(data.get("courses", [])))
        data["courses"] = dedupe(data.get("courses", []) + courses)

        if event.message and event.message.id > int(data.get("last_message_id", 0) or 0):
            data["last_message_id"] = event.message.id

        save(data)

        added = [c for c in courses if normalize_text(c) not in before]

        if added and data.get("phase") == "running":
            send_message(
                "📥 وصلت مقررات جديدة:\n" + "\n".join(f"- {c}" for c in added),
                keyboard=main_menu_keyboard(),
            )


async def backfill_history(client, channel):
    data = load()
    last_id = int(data.get("last_message_id", 0) or 0)
    newest = last_id
    changed = False

    async for msg in client.iter_messages(channel, reverse=True, min_id=last_id):
        courses = extract_courses(msg.raw_text or "")

        if courses:
            before = set(dedupe(data.get("courses", [])))
            data["courses"] = dedupe(data.get("courses", []) + courses)
            if set(data["courses"]) != before:
                changed = True

        if msg.id > newest:
            newest = msg.id

    if newest > last_id:
        data["last_message_id"] = newest
        changed = True

    if changed:
        save(data)

    return len(data.get("courses", []))
