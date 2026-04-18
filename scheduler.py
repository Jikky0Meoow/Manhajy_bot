import time

from bot_api import send_daily_batch
from planner import now_amman
from storage import load, save


def run_scheduler():
    while True:
        try:
            data = load()
            now = now_amman()

            # لازم يكون النظام جاهز
            if data.get("phase") != "running":
                time.sleep(15)
                continue

            today = now.date().isoformat()

            # إذا أرسل اليوم بالفعل → لا تعيد
            if data.get("last_daily_date") == today:
                time.sleep(60)
                continue

            # نافذة الإرسال (20:00 → 20:10)
            if not (now.hour == 20 and 0 <= now.minute <= 10):
                time.sleep(20)
                continue

            print(f"[SCHEDULER] Sending batch at {now}")

            # إرسال المقررات
            send_daily_batch()

            # تأكيد الإرسال
            data = load()
            data["last_daily_date"] = today
            save(data)

            print("[SCHEDULER] Done.")

            # مهم: ننتظر حتى لا يعيد الإرسال داخل نفس الدقيقة
            time.sleep(70)

        except Exception as e:
            print("[S
