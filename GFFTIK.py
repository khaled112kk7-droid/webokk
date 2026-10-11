import time
from telegram import Bot
from playwright.sync_api import sync_playwright

# إعدادات بوت تليجرام
TELEGRAM_TOKEN = "8237661772:AAFzudgS6eQIPi7kXINSZTxo3o7S8F6Dfu4"
CHAT_ID = "881479054"
bot = Bot(token=TELEGRAM_TOKEN)

# الرابط الخاص بك
BOOKING_URL = "https://webook.com/blustore/ar/events/hilal-m5-27-29412/book"

# كوكيز الجلسة للتسجيل التلقائي (اختر الاسم والقيمة المستخرجة من Webook)
COOKIES = [
    {
        "name": "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d",  # استبدل باسم الكوكيز الخاص بتسجيل الدخول في webook
        "value": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiI2NzhmYmQ3MDRiMTk1NTg5MTEwYzczZDIiLCJqdGkiOiIzMTMzMTM3Mzg0NGRlMzAxMTgwZGQ5ZDIxNjZkNmY5ODBmZTBjYTk1ZjNjZWNiNjY4N2RjMjg4OWQxZTEzMGUwNzcwYTYzYjdkMjU0Y2M4YiIsImlhdCI6MTc5MTM4ODgxNy45Mjc0NCwibmJmIjoxNzkxMzg4ODE3LjkyNzQ0MSwiZXhwIjoxNzkxOTkzNjE3LjkyMjU2Niwic3ViIjoiNjk2Nzg0NjVlYzJiODcyNDkxMGY5YzkyIiwic2NvcGVzIjpbInF1ZXVlX2p1bXBfb25saW5lIl19.BppdtueGYqxjcV1Mi0WZK2cD6D7tf2uqhR-PXqXtmQQeiKt_wIjHDm5MR7_WhzwoR2pxf_9ISIDIqWl6nUtd_6bKmOeUXKYvm987HQpaDRl1-Pg4yc2mumhthm4KutA8Ccqcj5w1TmaGjWsyf33E7KjTcvgRD2zzHvDJS3Bxb1_a-AxnPNDHB3dDOQGOE4ab8N7qjUcy-CnqiO-i2xN_nlLx3BuZNtAaaUAdIdJiTImVN7mqO8C0Rz5KDnar3nvy764KdQ1GVBm94ut0VyBwDoDUf4oUxGrq3Cw8Ge7-W7GX_92LKpcDIZ9hbv328Tz2rkf7jId-gWngpCad5QDRvZUnG2jf8nuYD37XnHuPmC7bm16jDIi-dhjfnqQz0r5CZOwGou96gBuXyIgroWn3qN5Qr3jx3s6JAb_MVoec0Dvym2gjciWpf5odSA6HUiVohyr4rdhpR0PJXu4eLZykqyuI4KhfdhbnzZpEgQMNXsIdi0TA6ZzBGNUUz781fcHq_3DPRvEwE8kenjsrcnvUZQkrVm2vqGyNdqgzyXZPDmd_t64UQu7UyFhacl39jwHYUOIwqp3XoubMjohK0XwvG9Uen4cMOS1XnvLZF1NiZncz-HZKKyxMUrJp7qtWPT61d4GOY-foNJC33c3Rb3rKh9sUNdoQ5o2TqcsMBONmFv0",
        "domain": ".webook.com",
        "path": "/",
    }
]


def send_telegram_alert_with_photo(message, photo_path):
  try:
    bot.send_message(chat_id=CHAT_ID, text=message)
    with open(photo_path, "rb") as photo_file:
      bot.send_photo(chat_id=CHAT_ID, photo=photo_file)
    print("تم إرسال التنبيه والصورة بنجاح عبر تليجرام.")
  except Exception as e:
    print(f"فشل إرسال التنبيه: {e}")


def monitor_webook_tickets():
  with sync_playwright() as p:
    # تشغيل المتصفح (يمكنك جعل headless=True إذا كنت لا ترغب برؤية النافذة)
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )

    # حقن الكوكيز لضمان الحفاظ على تسجيل الدخول
    context.add_cookies(COOKIES)

    page = context.new_page()

    while True:
      try:
        print("جاري فحص توفر التذاكر في Webook...")
        page.goto(BOOKING_URL, wait_until="domcontentloaded")

        # فحص وجود زر اختيار المقاعد أو الشراء
        # في Webook زر الشراء عادة يحمل نص "احجز الآن" أو "حجز التذاكر" أو اختيار الفئة
        booking_button = page.locator(
            "button:has-text('احجز'), button:has-text('شراء'),"
            " text='اختر المقاعد'"
        )

        # التحقق من أن الزر متاح وليس معطلاً (Disabled)
        if booking_button.is_visible() and booking_button.is_enabled():
          print("🚨 التذاكر متاحة الآن!")

          screenshot_path = "webook_ticket_available.png"
          page.screenshot(path=screenshot_path, full_page=True)

          send_telegram_alert_with_photo(
              f"🚨 تنبيه عاجل: فتح حجز تذاكر الهلال الآن!\nالرابط:"
              f" {BOOKING_URL}",
              screenshot_path,
          )

          # التوقف عن التكرار بعد اكتشاف التذاكر
          break
        else:
          print("التذاكر غير متاحة حتى الآن (أو في قائمة الانتظار)...")

      except Exception as e:
        print(f"حدث خطأ أثناء الفحص: {e}")

      # سرعة الفحص (بالثواني)
      time.sleep(10)

    # إبقاء النافذة مفتوحة لتتمكن من إكمال الحجز يدويًا فوريًا
    page.pause()


if __name__ == "__main__":
  monitor_webook_tickets()
