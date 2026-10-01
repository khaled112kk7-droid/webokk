import os
import asyncio
import requests

# استدعاء المتغيرات البيئية من GitHub Secrets
EMAIL = os.getenv("WEBOOK_EMAIL") or os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

EVENT_URL = "https://webook.com/ar/SA/RUH/sports-event/events/rsl-26-27-al-shabab-vs-al-hilal-227984/book"

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

            # --- فحص اختفاء كلمة 'نورتنا' ---
            is_disappeared = await check_welcome_message_disappeared(page)

            if is_disappeared:
                report += "🎉 تم فك الأولوية لتذاكر - الهلال و القادسية"
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
            print("🏁 إغلاق المتصفح وإنهاء السكربت.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
