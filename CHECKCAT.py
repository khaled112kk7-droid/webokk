import os
import io
import asyncio
import requests
from PIL import Image
from playwright.async_api import async_playwright

# استدعاء المتغيرات من البيئة (GitHub Secrets)
EMAIL = os.getenv("WEBOOK_EMIL") or os.getenv("WEBOOK_EMAIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

EVENT_URL = "https://webook.com/ar/SA/dam/sports-event/events/alqadsiah-vs-al-hilal-tickets-26-27/book"

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
    
    print("❌ فشل إرسال الصورة بعد عدة محاولات، جاري إرسال التقرير كنص...")
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
    """
    يفحص ما إذا كانت كلمة 'نورتنا' قد اختفت من الصفحة أم لا.
    """
    print("🔍 جاري التحقق من وجود كلمة 'نورتنا' في الصفحة...")
    await page.wait_for_timeout(2000)

    # البحث عن كلمة "نورتنا" داخل محتوى الصفحة
    has_welcome_text = await page.evaluate("""() => {
        return document.body.innerText.includes('نورتنا');
    }""")

    if not has_welcome_text:
        print("🚨 كلمة 'نورتنا' اختفت! التذاكر أو الصفحة قد تكون فتحت الان!")
        return True
    else:
        print("⏳ كلمة 'نورتنا' لا تزال موجودة (الصفحة لم تفتح بعد).")
        return False

async def run_monitor():
    async with async_playwright() as p:
        print("🚀 بدء تشغيل المتصفح...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        try:
            print("🌐 [خطوة 1] الانتقال لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="networkidle")
            await close_cookie_banner(page)

            # --- تسجيل الدخول ---
            email_input = page.locator("input[type='email'], input[placeholder*='you@email.com']").first
            if await email_input.is_visible(timeout=5000):
                print("📧 [خطوة 2] إدخال البريد الإلكتروني...")
                await email_input.fill(str(EMAIL))
                await page.wait_for_timeout(1000)

                try:
                    await email_input.press("Enter")
                except Exception:
                    continue_btn = page.locator("button:has-text('تابع باستخدام البريد الإلكتروني')").first
                    await continue_btn.click(force=True)

                password_input = page.locator("input[type='password']").first
                await password_input.wait_for(timeout=15000)
                print("🔑 [خطوة 3] إدخال كلمة المرور...")
                await password_input.fill(str(PASSWORD))
                await page.wait_for_timeout(1000)

                try:
                    await password_input.press("Enter")
                except Exception:
                    login_btn = page.locator("button:has-text('تسجيل الدخول')").first
                    await login_btn.click(force=True)

                await page.wait_for_timeout(4000)

            # --- الفحص بعد تسجيل الدخول ---
            is_disappeared = await check_welcome_message_disappeared(page)

            if is_disappeared:
                report = "🚨 *تنبيه عاجل!*\n\n"
                report += "🎉 تم فك الأولوية لتذاكر - الهلال و القادسية"
                
                await page.screenshot(path="opened_page.png")
                send_telegram_photo("opened_page.png", f"⚡ *تغيّر في حالة الصفحة!*\n\n{report}")
            else:
                report = "ℹ️ *حالة الفحص:*\n\n"
                report += "لا تزال رسالة 'نورتنا، بس جيت بدري شوي!' ظاهرة ولم تفتح الصفحة بعد."
                
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
            print("🏁 إغلاق المتصفح وإنهاء السكربت.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
