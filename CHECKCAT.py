import os
import io
import asyncio
import json
import requests
from PIL import Image
from playwright.async_api import async_playwright

# --- إعدادات المتغيرات (يفضل وضعها في GitHub Secrets) ---
# للأغراض التجريبية، يمكنك كتابة القيم مباشرة هنا، لكن لا تشارك الملف مع أحد.
PHONE = os.getenv("WEBOOK_EMAIL") or "your_email@example.com"
PASSWORD = os.getenv("WEBOOK_PASS") or "your_password"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "your_bot_token"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "your_chat_id"
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY") or "" # اختياري إذا واجهت كابتشا

# رابط الفعالية المحدد
EVENT_URL = "https://webook.com/ar/sa/jed/sports-event/events/rsl-al-ittihad-vs-al-nassr-050926/book"
TARGET_TEAM = "الاتحاد"

# قائمة المربعات المطلوبة للفحص وإحداثياتها التقريبية داخل الخريطة (Canvas)
# الإحداثيات هي نسب مئوية من عرض وارتفاع الخريطة
TARGET_SECTIONS = {
    "525": {"x_min": 0.62, "x_max": 0.66, "y_min": 0.18, "y_max": 0.22},
    "323": {"x_min": 0.62, "x_max": 0.66, "y_min": 0.23, "y_max": 0.27},
    "322": {"x_min": 0.66, "x_max": 0.70, "y_min": 0.23, "y_max": 0.27}
}

# اللون الرمادي الذي يدل على نفاذ التذاكر
SOLD_OUT_COLOR = (30, 30, 30)
COLOR_THRESHOLD = 5 # سماحية الاختلاف في درجات اللون (للاحتياط)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ فشل إرسال تنبيه التليجرام: {e}")

def send_telegram_photo(photo_path, caption="📸 لقطة شاشة من الفحص"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            files = {"photo": photo}
            requests.post(url, data=payload, files=files, timeout=30)
            print("📬 تم إرسال الصورة إلى التليجرام.")
    except Exception as e:
        print(f"❌ فشل إرسال الصورة: {e}")
        send_telegram_message(caption) # إرسال النص فقط كبديل

async def handle_response(response):
    # وظيفة لمراقبة استجابات الشبكة (اختياري، قد تفيد في رصدSiteKey الكابتشا)
    pass

# --- دالة الفحص البصري لمنطق "نفذت" الجديد ---
async def check_sold_out_status(page):
    """
    التقاط الخريطة بصرياً وفحص المربعات المحددة.
    إذا تم رصد لون RGB(30, 30, 30)، يُعتبر المربع "نفذت".
    """
    print("🔍 جاري التحقق البصري من حالة نفاذ التذاكر (RGB 30,30,30)...")
    await page.wait_for_timeout(3000)

    # الوصول إلى iframe الخريطة
    frame = page.frame(name="seats-iframe") or page.frame(url=lambda u: "seatcloud" in u or "seats" in u)
    target = frame if frame else page

    canvas_elem = await target.query_selector('canvas#canvas, canvas')
    if not canvas_elem:
        print("⚠️ لم يتم العثور على عنصر Canvas داخل الخريطة.")
        return {}

    # التقاط صورة للخريطة فقط
    screenshot_bytes = await canvas_elem.screenshot()
    img = Image.open(io.BytesIO(screenshot_bytes))
    img = img.convert('RGB') # التأكد من صيغة RGB
    width, height = img.size

    sections_results = {}

    for sec_name, bounds in TARGET_SECTIONS.items():
        x_min, x_max = int(width * bounds["x_min"]), int(width * bounds["x_max"])
        y_min, y_max = int(height * bounds["y_min"]), int(height * bounds["y_max"])

        sold_out_pixels = 0
        total_pixels_in_range = (x_max - x_min) * (y_max - y_min)

        # مسح البكسلات داخل حدود المربع
        for x in range(x_min, x_max):
            for y in range(y_min, y_max):
                r, g, b = img.getpixel((x, y))

                # التحقق مما إذا كان اللون قريباً جداً من الرمادي الداكن المحدد
                if (abs(r - SOLD_OUT_COLOR[0]) <= COLOR_THRESHOLD and
                    abs(g - SOLD_OUT_COLOR[1]) <= COLOR_THRESHOLD and
                    abs(b - SOLD_OUT_COLOR[2]) <= COLOR_THRESHOLD):
                    sold_out_pixels += 1

        # منطق "نفذت": إذا طغى اللون الرمادي على المربع
        # (استخدام نسبة 70% للتأكد من أن المربع بالكامل تقريباً رمادي)
        if total_pixels_in_range > 0:
            sold_out_ratio = sold_out_pixels / total_pixels_in_range
            is_sold_out = sold_out_ratio > 0.70 
        else:
            is_sold_out = False

        sections_results[sec_name] = is_sold_out
        status_text = "❌ نفذت" if is_sold_out else "✅ متاح أو لون آخر"
        print(f"📊 المربع {sec_name}: {status_text} (نسبة الرمادي الداكن: {sold_out_pixels}/{total_pixels_in_range})")

    return sections_results

async def run_monitor():
    async with async_playwright() as p:
        print("🚀 بدء المتصفح...")
        browser = await p.chromium.launch(headless=True) # اجعله False إذا أردت رؤية ما يحدث
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        page.on("response", handle_response)

        try:
            print("🌐 [1] الانتقال لصفحة حجز التذاكر...")
            await page.goto(EVENT_URL, wait_until="networkidle")

            # --- هنا يجب إضافة كود تسجيل الدخول واختيار الفريق ---
            # بسبب ديناميكية الموقع، يجب كتابة الكود المناسب هنا للوصول للخريطة.
            # يمكنك استخدام الكود الذي نجح معك سابقاً للوصول إلى هذه المرحلة.
            print("⏳ (يجب كتابة كود تسجيل الدخول واختيار الفريق هنا للوصول للخريطة)...")
            # مثال افتراضي للانتظار حتى تحميل الخريطة
            await page.wait_for_selector('iframe[name="seats-iframe"]', timeout=30000)

            # --- حفظ لقطة شاشة الخريطة وفحص حالة المربعات بصرياً ---
            await page.screenshot(path="map_screenshot.png")
            
            sold_out_status = await check_sold_out_status(page)

            report = "📊 *تقرير فحص حالة التذاكر (RGB 30,30,30):*\n\n"
            available_sections = []

            for sec, is_sold_out in sold_out_status.items():
                if is_sold_out:
                    report += f"❌ *المربع `{sec}`:* نفذت التذاكر (رمادي).\n"
                else:
                    report += f"✅ *المربع `{sec}`:* متاح أو لون آخر غير الرمادي الداكن.\n"
                    available_sections.append(sec)

            # تحضير التنبيه النهائي
            if available_sections:
                final_caption = f"🏁 *نتائج الفحص:* وجدنا مربعات محتملة المتاحة: {', '.join(available_sections)}\n\n{report}"
            else:
                final_caption = f"🏁 *نتائج الفحص:* جميع المربعات المطلوبة نفذت.\n\n{report}"

            send_telegram_photo("map_screenshot.png", final_caption)

        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع: {e}")
            await page.screenshot(path="error_screenshot.png")
            send_telegram_photo("error_screenshot.png", f"❌ توقف السكربت بسبب خطأ:\n`{e}`")
        finally:
            print("🏁 إغلاق المتصفح.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
