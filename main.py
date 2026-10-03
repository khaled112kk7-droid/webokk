import os
import sys
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ فشل إرسال التنبيه عبر التليجرام: {e}")

def send_telegram_photo(photo_path, caption="📸 صورة من السكربت"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ توكن التليجرام أو Chat ID غير معرف بشكل صحيح.")
        return False

    for attempt in range(3):
        try:
            with open(photo_path, "rb") as photo:
                payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
                files = {"photo": ("screenshot.png", photo, "image/png")}
                res = requests.post(url, data=payload, files=files, timeout=30)
                if res.status_code == 200:
                    print("📬 تم إرسال الصورة والتنبيه إلى التليجرام بنجاح!")
                    return True
                else:
                    print(f"⚠️ استجابة التليجرام: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"⚠️ محاولة ({attempt + 1}/3) فشلت لإرسال الصورة: {e}")
            import time
            time.sleep(2)
    
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

async def is_welcome_disappeared(page):
    try:
        # 1. انتظار استقرار الشبكة لضمان اكتمال بناء الصفحة
        await page.wait_for_load_state("networkidle", timeout=7000)
    except Exception:
        pass

    # 2. الفحص الأول
    has_welcome_first = await page.evaluate("() => document.body.innerText.includes('نورتنا')")
    
    # 3. إذا لم تجد الكلمة، ننتظر 2.5 ثانية ونفحص للمرة الثانية للتأكد القطعي
    if not has_welcome_first:
        print("🔍 لم تظهر الكلمة في الفحص الأول.. جاري التأكد مرة أخرى خلال 2.5 ثانية...")
        await page.wait_for_timeout(2500)
        has_welcome_second = await page.evaluate("() => document.body.innerText.includes('نورتنا')")
        return not has_welcome_second

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
            email_input = page.locator("input[type='email'], input[name='email']").first
            try:
                await email_input.wait_for(state="visible", timeout=10000)
                print("📧 إدخال البريد الإلكتروني...")
                await email_input.click()
                await email_input.fill("")
                await email_input.type(str(EMAIL), delay=50)
                await page.wait_for_timeout(1000)

                await email_input.press("Enter")
                await page.wait_for_timeout(1500)

                submit_btn = page.locator("button:has-text('تابع باستخدام البريد الإلكتروني'), button:has-text('تابع')").first
                if await submit_btn.is_visible(timeout=3000):
                    await submit_btn.click(force=True)

                await page.wait_for_timeout(2500)
            except Exception as e:
                print(f"❌ فشلت خطوة البريد الإلكتروني: {e}")
                return

            password_input = page.locator("input[type='password'], input[name='password']").first
            try:
                await password_input.wait_for(state="visible", timeout=15000)
                print("🔑 إدخال كلمة المرور...")
                await password_input.click()
                await password_input.fill("")
                await password_input.type(str(PASSWORD), delay=50)
                await page.wait_for_timeout(1000)

                await password_input.press("Enter")

                login_btn = page.locator("button:has-text('تسجيل الدخول')").first
                if await login_btn.is_visible(timeout=3000):
                    await login_btn.click(force=True)

                await page.wait_for_timeout(4000)
                await close_cookie_banner(page)
                print("✅ تم تسجيل الدخول بنجاح والوصول لصفحة الفعالية!")
            except Exception as e:
                print(f"❌ فشلت خطوة كلمة المرور: {e}")
                return

            # --- حلقة التحديث والفحص ---
            print("🔄 بدء حلقة التحديث والفحص...")
            
            for iteration in range(1, 11):
                print(f"🔍 المحاولة ({iteration}/10): فحص الصفحة...")

                disappeared = await is_welcome_disappeared(page)

                if disappeared:
                    print("🚨 اختفت كلمة 'نورتنا' مؤكداً! جاري إرسال التنبيه الفوري وإيقاف الفحص...")
                    report = f"إنتهت الأولوية لتذاكر الهلال والقادسية\n\n🔗 رابط الحجز:\n{EVENT_URL}"
                    
                    await page.screenshot(path="tickets_open.png")
                    send_telegram_photo("tickets_open.png", report)
                    
                    with open("stop_signal.txt", "w") as f:
                        f.write("STOP")

                    break
                else:
                    print(f"⏳ المحاولة ({iteration}/10): كلمة 'نورتنا' لا تزال موجودة.")

                if iteration < 10:
                    print("⏱️ انتظار 10 ثوانٍ قبل التحديث القادم...")
                    await page.wait_for_timeout(10000)
                    print("🔄 إعادة تحديث الصفحة (Reload)...")
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع أثناء الفحص: {e}")
        finally:
            print("🏁 إغلاق المتصفح وإنهاء عملية الفحص.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(perform_check())
