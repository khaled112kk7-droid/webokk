import os
import asyncio
import requests
from playwright.async_api import async_playwright

# استدعاء المتغيرات البيئية المطابقة لـ GitHub Secrets
EMAIL = os.getenv("WEBOOK_EMAIL") or os.getenv("WEBOOK_EMIL")
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
    for attempt in range(3):
        try:
            with open(photo_path, "rb") as photo:
                payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
                files = {"photo": photo}
                res = requests.post(url, data=payload, files=files, timeout=30)
                if res.status_code == 200:
                    print("📬 تم إرسال الصورة إلى التليجرام بنجاح!")
                    return True
        except Exception as e:
            print(f"⚠️ محاولة ({attempt + 1}/3) فشلت لإرسال الصورة: {e}")
            import time
            time.sleep(2)
    
    print("❌ فشل إرسال الصورة، جاري إرسال التقرير كنص...")
    send_telegram(caption)
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
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
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

            # --- تسجيل الدخول ---
            email_input = page.locator("input[type='email'], input[name='email'], input[placeholder*='you@email.com']").first
            if await email_input.is_visible(timeout=5000):
                print("📧 جاري إدخال البريد الإلكتروني...")
                await email_input.click()
                await email_input.type(str(EMAIL), delay=50)
                await page.wait_for_timeout(1000)

                await email_input.press("Enter")
                try:
                    continue_btn = page.locator("button:has-text('تابع باستخدام البريد الإلكتروني'), button[type='submit']").first
                    if await continue_btn.is_visible(timeout=2000):
                        await continue_btn.click(force=True)
                except Exception:
                    pass

                print("⏳ انتظار ظهور خانة كلمة المرور...")
                await page.wait_for_timeout(3000)

                password_input = page.locator("input[type='password'], input[name='password']").first
                await password_input.wait_for(state="visible", timeout=15000)
                print("🔑 جاري إدخال كلمة المرور...")
                await password_input.type(str(PASSWORD), delay=50)
                await page.wait_for_timeout(1000)

                await password_input.press("Enter")
                try:
                    login_btn = page.locator("button:has-text('تسجيل الدخول'), button[type='submit']").first
                    if await login_btn.is_visible(timeout=2000):
                        await login_btn.click(force=True)
                except Exception:
                    pass

                await page.wait_for_timeout(4000)
                print("تمت محاولة تسجيل الدخول بنجاح!")
                await close_cookie_banner(page)

            # --- فحص اختفاء كلمة 'نورتنا' ---
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
            print(f"❌ حدث خطأ أثناء التنفيذ: {e}")
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
