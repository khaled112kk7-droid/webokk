import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

# 1. جلب البيانات من متغيرات البيئة السريّة (Environment Variables)
PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 2. إعدادات الفعالية والفئات المطلوب مراقبتها
EVENT_URL = "https://webook.com/ar/events/events/rsl-26-27-al-shabab-vs-al-hilal-227984/book" # استبدله برابط الفعالية
TEAM_NAME = "الهلال" # اسم زر الفريق لتحديده (أو اتركه فارغاً "" إذا لم يوجد)
TARGET_CATEGORIES = ["Premium 2", "Premium"] # اسم الفئتين المراد حسابهما

# متغير تخزين المقاعد المستخرجة من الـ API
seats_data_store = []

def send_telegram(message):
    """إرسال التنبيه فوراً إلى التليجرام"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"فشل إرسال التنبيه عبر التليجرام: {e}")

async def handle_response(response):
    """التقاط الـ API الخاص بخريطة المقاعد أثناء التحميل واستخراج بيانات المقاعد"""
    global seats_data_store
    if "seat" in response.url or "map" in response.url or "layout" in response.url:
        try:
            if response.status == 200 and "json" in response.headers.get("content-type", ""):
                data = await response.json()
                # البحث عن مصفوفة المقاعد داخل الـ JSON
                if isinstance(data, dict):
                    seats_data_store = data.get("seats", data.get("data", []))
                elif isinstance(data, list):
                    seats_data_store = data
        except Exception:
            pass

async def run_monitor():
    global seats_data_store
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # استماع للطلبات الشبكية لاقتناص استجابة خريطة المقاعد
        page.on("response", handle_response)

        try:
            # الخطوة 1: تسجيل الدخول
            print("جاري تسجيل الدخول...")
            await page.goto("https://webook.com/ar/login")
            await page.fill("input[type='tel']", PHONE)
            await page.fill("input[type='password']", PASSWORD)
            await page.click("button[type='submit']")
            await page.wait_for_navigation(timeout=15000)

            # الخطوة 2: الانتقال لصفحة الفعالية
            print("الانتقال لصفحة الفعالية...")
            await page.goto(EVENT_URL)

            # الخطوة 3: اختيار الفريق (إن وجد)
            if TEAM_NAME:
                try:
                    team_btn = page.locator(f"text='{TEAM_NAME}'")
                    if await team_btn.is_visible():
                        await team_btn.click()
                except Exception:
                    pass

            # الانتظار لحين تحميل عناصر الفئات/الخريطة
            await page.wait_for_timeout(5000)

            # الخطوة 4: معالجة البيانات واستخراج أعداد المقاعد المتبقية لكل فئة
            report = "📊 *تقرير المقاعد المتاحة في ويبوك:*\n\n"
            send_alert = False

            # أ) إذا تم اقتناص بيانات الخريطة برمجياً (الأدق بالعدد)
            if seats_data_store:
                for category in TARGET_CATEGORIES:
                    # فلترة المقاعد المتاحة التي تنتمي للفئة المحددة
                    available_count = len([
                        s for s in seats_data_store 
                        if s.get("status") == "AVAILABLE" and category.lower() in str(s.get("category", "")).lower()
                    ])
                    
                    report += f"🔹 *{category}:* متبقي `{available_count}` مقعد.\n"
                    if available_count > 0:
                        send_alert = True

            # ب) إذا لم نلتقط الخريطة، نعتمد على القراءة البصرية للصفحة
            else:
                for category in TARGET_CATEGORIES:
                    cat_locator = page.locator(f"text='{category}'")
                    if await cat_locator.is_visible():
                        parent_card = cat_locator.locator("xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'item')][1]")
                        text = await parent_card.inner_text()
                        
                        if "نفدت" in text or "Sold Out" in text:
                            report += f"❌ *{category}:* نفدت بالكامل.\n"
                        else:
                            report += f"✅ *{category}:* متاحة الآن للحجز!\n"
                            send_alert = True
                    else:
                        report += f"⚠️ *{category}:* غير ظاهرة بالقائمة.\n"

            # الخطوة 5: إرسال التنبيه
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
