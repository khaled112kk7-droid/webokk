import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

EVENT_URL = "https://webook.com/ar/SA/RUH/sports-event/events/rsl-26-27-al-shabab-vs-al-hilal-227984/book"
TARGET_CATEGORIES = ["Premium", "Premium 2"]

seats_data_store = []

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"فشل إرسال التنبيه عبر التليجرام: {e}")

async def handle_response(response):
    global seats_data_store
    if "seat" in response.url or "map" in response.url or "layout" in response.url:
        try:
            if response.status == 200 and "json" in response.headers.get("content-type", ""):
                data = await response.json()
                if isinstance(data, dict):
                    seats_data_store = data.get("seats", data.get("data", []))
                elif isinstance(data, list):
                    seats_data_store = data
        except Exception:
            pass

async def close_cookie_banner(page):
    try:
        cookie_btn = page.locator("button:has-text('قبول الكل'), button:has-text('رفض الكل')").first
        if await cookie_btn.is_visible(timeout=2000):
            await cookie_btn.click(force=True)
    except Exception:
        pass

async def run_monitor():
    global seats_data_store
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        page.on("response", handle_response)

        try:
            # --- تسجيل الدخول والانتظار التلقائي للتوجيه ---
            print("جاري فتح صفحة تسجيل الدخول...")
            await page.goto("https://webook.com/ar/login", wait_until="domcontentloaded", timeout=60000)
            await close_cookie_banner(page)

            email_input = page.locator("input[type='email'], input[placeholder*='you@email.com']").first
            await email_input.wait_for(timeout=15000)
            await email_input.fill(str(PHONE))

            try:
                await email_input.press("Enter")
            except Exception:
                await page.locator("button:has-text('تابع باستخدام البريد الإلكتروني')").first.click(force=True)

            password_input = page.locator("input[type='password']").first
            await password_input.wait_for(timeout=15000)
            await password_input.fill(str(PASSWORD))

            print("جاري تسجيل الدخول والانتظار حتى الانتقال التلقائي...")
            try:
                await password_input.press("Enter")
            except Exception:
                await page.locator("button:has-text('تسجيل الدخول')").first.click(force=True)

            # الانتظار التلقائي لحين تغيير رابط الصفحة بعد تسجيل الدخول
            await page.wait_for_url(lambda url: "login" not in url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            print("تم تسجيل الدخول والتوجيه بنجاح!")

            # --- خطوة واحدة: فتح الفعالية واختيار الفريق والمتابعة ---
            print("الانتقال لصفحة الفعالية واختيار الفريق...")
            await page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=60000)
            await close_cookie_banner(page)

            await page.get_by_text("الهلال", exact=False).first.click(force=True)
            
            agree_checkbox = page.locator("input[type='checkbox'], [role='checkbox']").first
            if await agree_checkbox.is_visible(timeout=3000):
                if not await agree_checkbox.is_checked():
                    await agree_checkbox.click(force=True)

            await page.locator("button:has-text('التالي'), button:has-text('اختيار التذاكر')").first.click(force=True)

            await page.wait_for_timeout(4000)

            # --- فحص المقاعد ---
            report = "📊 *تقرير المقاعد المتاحة (الهلال ضد الشباب):*\n\n"
            send_alert = False

            if seats_data_store:
                for category in TARGET_CATEGORIES:
                    available_count = len([
                        s for s in seats_data_store 
                        if s.get("status") == "AVAILABLE" and category.lower() in str(s.get("category", "")).lower()
                    ])
                    report += f"🔹 *{category}:* متبقي `{available_count}` مقعد.\n"
                    if available_count > 0:
                        send_alert = True
            else:
                for category in TARGET_CATEGORIES:
                    cat_locator = page.locator(f"text='{category}'")
                    if await cat_locator.is_visible():
                        parent_card = cat_locator.locator("xpath=ancestor::div[1]")
                        text = await parent_card.inner_text()
                        if "نفدت" in text or "Sold Out" in text:
                            report += f"❌ *{category}:* نفدت بالكامل.\n"
                        else:
                            report += f"✅ *{category}:* متاحة الآن للحجز!\n"
                            send_alert = True
                    else:
                        report += f"⚠️ *{category}:* غير ظاهرة بالقائمة.\n"

            if send_alert:
                send_telegram(report)
                print("تم إرسال التقرير للتليجرام بنجاح!")
            else:
                print("لا توجد مقاعد متاحة للفئات المحددة حالياً.")

        except Exception as e:
            print(f"حدث خطأ أثناء تنفيذ السكربت: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
