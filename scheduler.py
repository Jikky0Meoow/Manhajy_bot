import time

from bot_api import send_daily_batch
from planner import now_amman
from storage import load, save


def run_scheduler():
    while True:
        try:
            data = load()
            now = now_amman()

            # إذا لسا ما خلص الإعداد
            if data.get("phase") != "running":
                time.sleep(20)
                continue

            today = now.date().isoformat()

            # إذا أرسل اليوم بالفعل
            if data.get("last_daily_date") == today:
                time.sleep(60)
                continue

            # فقط بين 20:00 و 20:10
            if not (now.hour == 20 and now.minute <= 10):
                time.sleep(30)
                continue

            print("Sending daily batch...")

            send_daily_batch()

            data = load()
            data["last_daily_date"] = today
            save(data)

            print("Daily batch sent.")

            time.sleep(60)

        except Exception as e:
            print("ERROR in scheduler:", e)
            time.sleep(5)
