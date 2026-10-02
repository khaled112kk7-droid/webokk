import os
import asyncio
import requests
from playwright.async_api import async_playwright

EMAIL = os.getenv("WEBOOK_EMAIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELE_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELE_CHAT_ID")

EVENT_URL = "https://webook.com/ar/sa/dam/sports-event/events/alqadsiah-vs-al-hilal-tickets-26-27/book"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ فشل إرسال التنبيه عبر التليجرام: {e}")

def send_telegram_photo(photo_path, caption="📸 صورة من السكربت"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ توكن التليجرام أو Chat ID غير معرف بشكل صحيح في المتغيرات البيئية.")
        return False

    for attempt in range(3):
        try:
            with open(photo_path, "rb") as photo:
                payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
                files = {"photo": ("screenshot.png", photo, "image/png")}
                res = requests.post(url, data=payload, files=files, timeout=30)
                if res.status_code == 200:
                    print("📬 تم إرسال الصورة إلى التليجرام بنجاح!")
                    return True
                else:
                    print(f"⚠️ استجابة التليجرام: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"⚠️ محاولة ({attempt + 1}/3) فشلت لإرسال الصورة: {e}")
            import time
            time.sleep(2)
    
    print("❌ فشل إرسال الصورة، جاري إرسال التقرير كنص...")
    send_telegram(f"{caption}\n\n(تعذر إرفاق صورة الشاشة)")
    return False

async def close_cookie_banner(page):
    try:
        cookie_btn = page.locator("button:has-text('قبول الكل'), button:has-text('رفض الكل الغير ضروري')").first
        if await cookie_btn.is_visible(timeout=3000):
            await cookie_btn.click(force=True)
            print("🍪 تم إغلاق إشعار الكوكيز.")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def check_welcome_message_disappeared(page):
    print("🔍 جاري التحقق من وجود كلمة 'نورتنا' في الصفحة...")
    await page.wait_for_timeout(2000)

    has_welcome_text = await page.evaluate("""() => {
        return document.body.innerText.includes('نورتنا');
    }""")

    if not has_welcome_text:
        print("🚨 كلمة 'نورتنا' اختفت! التذاكر أو الصفحة أصبحت متاحة الآن!")
        return True
    else:
        print("⏳ كلمة 'نورتنا' لا تزال موجودة.")
        return False

async def perform_check():
    async with async_playwright() as p:
        print("🚀 بدء تشغيل المتصفح...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            print("🌐 الانتقال المباشر لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await close_cookie_banner(page)

            # --- الخطوة 1: إدخال البريد الإلكتروني ---
            email_input = page.locator("input[type='email'], input[name='email'], input[placeholder*='you@email.com']").first
            try:
                await email_input.wait_for(state="visible", timeout=10000)
                print("📧 جاري إدخال البريد الإلكتروني...")
                await email_input.click()
                await email_input.fill(str(EMAIL))
                await page.wait_for_timeout(1000)

                # محاولة الضغط على زر المتابعة الصريح أولاً ثم Enter
                continue_btn = page.locator("button:has-text('تابع'), button:has-text('متابعة'), button[type='submit']").first
                if await continue_btn.is_visible(timeout=3000):
                    await continue_btn.click(force=True)
                else:
                    await email_input.press("Enter")
                
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"❌ فشلت خطوة إدخال البريد: {e}")
                await page.screenshot(path="step1_email_failed.png")
                send_telegram_photo("step1_email_failed.png", f"❌ فشلت خطوة إدخال البريد الإلكتروني:\n`{e}`")
                return

            # --- الخطوة 2: انتظار وإدخال كلمة المرور ---
            print("⏳ انتظار ظهور خانة كلمة المرور...")
            password_input = page.locator("input[type='password'], input[name='password']").first
            try:
                await password_input.wait_for(state="visible", timeout=12000)
                print("🔑 جاري إدخال كلمة المرور...")
                await password_input.click()
                await password_input.fill(str(PASSWORD))
                await page.wait_for_timeout(1000)

                login_btn = page.locator("button:has-text('تسجيل الدخول'), button[type='submit']").first
                if await login_btn.is_visible(timeout=3000):
                    await login_btn.click(force=True)
                else:
                    await password_input.press("Enter")

                await page.wait_for_timeout(4000)
                await close_cookie_banner(page)
            except Exception as e:
                print(f"❌ فشلت خطوة كلمة المرور: {e}")
                await page.screenshot(path="step2_password_failed.png")
                send_telegram_photo("step2_password_failed.png", "⚠️ فشلت خطوة كلمة المرور. إليك صورة الصفحة الحالية:")
                return

            # --- الخطوة 3: فحص اختفاء كلمة 'نورتنا' ---
            is_disappeared = await check_welcome_message_disappeared(page)

            if is_disappeared:
                report = "🚨 *تنبيه عاجل!*\n\n🎉 *اختفت رسالة 'نورتنا'!* قد تكون التذاكر أصبحت متاحة الآن."
                await page.screenshot(path="opened_page.png")
                send_telegram_photo("opened_page.png", f"⚡ *تغيّر في حالة الصفحة!*\n\n{report}")
            else:
                report = "ℹ️ *حالة الفحص:*\n\nلا تزال رسالة 'نورتنا، بس جيت بدري شوي!' ظاهرة."
                await page.screenshot(path="waiting_page.png")
                send_telegram_photo("waiting_page.png", report)

        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع: {e}")
            try:
                await page.screenshot(path="error_screenshot.png")
                send_telegram_photo("error_screenshot.png", f"❌ توقف السكربت عند الخطأ:\n`{e}`")
            except Exception as img_err:
                print(f"فشل إرسال الصورة: {img_err}")
        finally:
            print("🏁 إغلاق المتصفح وإنهاء الفحص.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(perform_check())
