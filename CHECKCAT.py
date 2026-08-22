import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

# 1. جلب البيانات السرية من متغيرات البيئة (GitHub Secrets)
PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 2. إعدادات الفعالية والفئات المطلوب مراقبتها
EVENT_URL = "https://webook.com/ar/SA/RUH/sports-event/events/rsl-26-27-al-shabab-vs-al-hilal-227984/book"
TARGET_CATEGORIES = ["Premium", "Premium 2"]

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
                if isinstance(data, dict):
                    seats_data_store = data.get("seats", data.get("data", []))
                elif isinstance(data, list):
                    seats_data_store = data
        except Exception:
            pass

async def close_cookie_banner(page):
    """إغلاق نافذة موافقة الكوكيز تلقائياً إذا ظهرت"""
    try:
        cookie_btn = page.locator("button:has-text('قبول الكل'), button:has-text('رفض الكل الغير ضروري')").first
        if await cookie_btn.is_visible(timeout=3000):
            await cookie_btn.click(force=True)
            print("تم إغلاق نافذة الكوكيز بنجاح.")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def run_monitor():
    global seats_data_store
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # الاستماع للطلبات الشبكية لاقتناص استجابة الخريطة
        page.on("response", handle_response)

        try:
            # --- الخطوة 1: الدخول المباشر لصفحة الفعالية ---
            print("الانتقال المباشر لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="networkidle")
            await close_cookie_banner(page)

            # --- الخطوة 2: تسجيل الدخول التلقائي في حال تم التوجيه لنماذج الدخول ---
            email_input = page.locator("input[type='email'], input[placeholder*='you@email.com']").first
            if await email_input.is_visible(timeout=5000):
                print("جاري إدخال البريد الإلكتروني...")
                await email_input.fill(str(PHONE))
                await page.wait_for_timeout(1000)

                try:
                    await email_input.press("Enter")
                except Exception:
                    continue_btn = page.locator("button:has-text('تابع باستخدام البريد الإلكتروني')").first
                    await continue_btn.click(force=True)

                password_input = page.locator("input[type='password']").first
                await password_input.wait_for(timeout=15000)
                print("جاري إدخال كلمة المرور...")
                await password_input.fill(str(PASSWORD))
                await page.wait_for_timeout(1000)

                try:
                    await password_input.press("Enter")
                except Exception:
                    login_btn = page.locator("button:has-text('تسجيل الدخول')").first
                    await login_btn.click(force=True)

                await page.wait_for_timeout(3000)
                print("تم تسجيل الدخول بنجاح داخل التدفق!")

                hilal_btn = page.locator("p.text-label-M:has-text('الهلال')").first
                await hilal_btn.wait_for(state="visible", timeout=15000)
                await hilal_btn.click(force=True)
                print("✅ تم النقر على (الهلال) بنجاح.")
                await page.wait_for_timeout(1000)

            # 2. النقر على (أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط)
            print("جاري النقر على (أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط)...")
            agree_btn = page.locator("text='أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط', button:has-text('أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط')").first
            await agree_btn.click(force=True)
            print("✅ تم النقر على (أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط) بنجاح.")
            await page.wait_for_timeout(1000)

            # 3. النقر على (التالي: اختيار التذاكر)
            print("جاري النقر على (التالي: اختيار التذاكر)...")
            next_btn = page.locator("button:has-text('التالي: اختيار التذاكر')").first
            await next_btn.click(force=True)
            print("✅ تم النقر على (التالي: اختيار التذاكر) بنجاح.")

            await page.wait_for_timeout(5000)

            # --- الخطوة 4: فحص المقاعد وتحديد الأعداد المتبقية ---
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
                        parent_card = cat_locator.locator("xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'item')][1]")
                        text = await parent_card.inner_text()
                        
                        if "نفدت" in text or "Sold Out" in text:
                            report += f"❌ *{category}:* نفدت بالكامل.\n"
                        else:
                            report += f"✅ *{category}:* متاحة الآن للحجز!\n"
                            send_alert = True
                    else:
                        report += f"⚠️ *{category}:* غير ظاهرة بالقائمة.\n"

            # --- الخطوة 5: إرسال التقرير عبر التليجرام ---
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
