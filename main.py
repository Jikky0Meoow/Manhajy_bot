from threading import Thread
import time
import requests

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import API_ID, API_HASH, CHANNEL_LINK, SESSION_STRING, PORT, BOT_TOKEN
from collector import register_collector, backfill_history
from bot_api import (
    send_startup_prompt,
    handle_text_message,
    handle_poll_answer,
    handle_callback_query,
)
from scheduler import run_scheduler
from web import app
from storage import load, save


client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


def run_web():
    app.run(host="0.0.0.0", port=PORT)


def run_update_loop():
    data = load()
    offset = int(data.get("offset", 0) or 0)

    while True:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 25,
                },
                timeout=35,
            )

            payload = response.json()

            if not payload.get("ok"):
                time.sleep(3)
                continue

            for update in payload.get("result", []):
                offset = update["update_id"] + 1

                data = load()
                data["offset"] = offset
                save(data)

                if "message" in update:
                    message = update["message"]
                    text = message.get("text", "")
                    chat_id = message.get("chat", {}).get("id", 0)

                    if text:
                        handle_text_message(text, chat_id=chat_id)

                if "poll_answer" in update:
                    handle_poll_answer(update)

                if "callback_query" in update:
                    # للتوافق مع أي رسائل inline قديمة فقط
                    handle_callback_query(update)

        except Exception as e:
            print("ERROR in update loop:", e)
            time.sleep(3)


async def bootstrap():
    if not API_ID or not API_HASH or not CHANNEL_LINK or not SESSION_STRING:
        raise RuntimeError("Missing required environment variables")

    await client.start()

    channel = await client.get_entity(CHANNEL_LINK)

    await backfill_history(client, channel)
    register_collector(client, channel)

    send_startup_prompt()

    print("System running...")
    print("Connected to:", getattr(channel, "title", "channel"))

    await client.run_until_disconnected()


if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    Thread(target=run_scheduler, daemon=True).start()
    Thread(target=run_update_loop, daemon=True).start()

    with client:
        client.loop.run_until_complete(bootstrap())
