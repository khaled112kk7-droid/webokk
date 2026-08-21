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
EVENT_URL = "https://webook.com/ar/sa/ruh/sports-event/events/rsl-26-27-al-shabab-vs-al-hilal-2279"
TARGET_CATEGORIES = ["CAT 1", "CAT 2"]  # عدل أسماء الفئات المطلوبة هنا

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
        if await cookie_btn.is_visible(timeout=5000):
            await cookie_btn.click(force=True)
            print("تم إغلاق نافذة الكوكيز بنجاح.")
            await page.wait_for_timeout(2000)
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
            # --- الخطوة 1: تسجيل الدخول ---
            print("جاري فتح صفحة تسجيل الدخول...")
            await page.goto("https://webook.com/ar/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # إغلاق نافذة الكوكيز إذا ظهرت
            await close_cookie_banner(page)

            # إدخال البريد الإلكتروني
            email_input = page.locator("input[type='email'], input[placeholder*='you@email.com']").first
            await email_input.wait_for(timeout=30000)
            await email_input.fill(str(PHONE))
            await page.wait_for_timeout(2000)

            # الضغط على زر "تابع باستخدام البريد الإلكتروني"
            try:
                await email_input.press("Enter")
            except Exception:
                continue_btn = page.locator("button:has-text('تابع باستخدام البريد الإلكتروني')").first
                await continue_btn.click(force=True)

            # إدخال كلمة المرور
            password_input = page.locator("input[type='password']").first
            await password_input.wait_for(timeout=30000)
            await password_input.fill(str(PASSWORD))
            await page.wait_for_timeout(2000)

            # الضغط على زر "تسجيل الدخول"
            try:
                await password_input.press("Enter")
            except Exception:
                login_btn = page.locator("button:has-text('تسجيل الدخول')").first
                await login_btn.click(force=True)

            await page.wait_for_timeout(5000)
            print("تم تسجيل الدخول بنجاح!")

            # --- الخطوة 2: الانتقال للفعالية واختيار الفريق بالمحددات المباشرة ---
            print("الانتقال لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="domcontentloaded")
            
            # زيادة وقت الانتظار لاستقرار تحميل الصفحة بالكامل (10 ثواني)
            await page.wait_for_timeout(10000)

            # إغلاق الكوكيز لو ظهرت
            await close_cookie_banner(page)

            # 1. اختيار بطاقة فريق الهلال عبر data-testid (رفع مهلة الانتظار إلى 60 ثانية)
            print("اختيار فريق الهلال...")
            hilal_card = page.locator("[data-testid='ui_toggle_favorite_team_651fdc90492867952e046ae2']").first
            await hilal_card.wait_for(state="visible", timeout=60000)
            await hilal_card.click(force=True)
            await page.wait_for_timeout(3000)

            # 2. تحديد زر "أوافق" عبر data-testid (رفع مهلة الانتظار إلى 30 ثانية)
            print("تحديد مربع الموافقة...")
            terms_checkbox = page.locator("[data-testid='ticketing_teams_terms_checkbox']").first
            await terms_checkbox.wait_for(state="visible", timeout=30000)
            await terms_checkbox.click(force=True)
            await page.wait_for_timeout(3000)

            # 3. الضغط على زر "التالي" عبر data-testid (رفع مهلة الانتظار إلى 30 ثانية)
            print("الضغط على زر التالي...")
            confirm_button = page.locator("[data-testid='ticketing_teams_confirm_team_button']").first
            await confirm_button.wait_for(state="visible", timeout=30000)
            await confirm_button.click(force=True)

            # الانتظار لحين تحميل خريطة المقاعد والفئات
            await page.wait_for_timeout(8000)

            # --- الخطوة 3: فحص المقاعد وتحديد الأعداد المتبقية ---
            report = "📊 *تقرير المقاعد المتاحة (الهلال ضد الشباب):*\n\n"
            send_alert = False

            # أ) في حال اقتناص بيانات الخريطة من API
            if seats_data_store:
                for category in TARGET_CATEGORIES:
                    available_count = len([
                        s for s in seats_data_store 
                        if s.get("status") == "AVAILABLE" and category.lower() in str(s.get("category", "")).lower()
                    ])
                    
                    report += f"🔹 *{category}:* متبقي `{available_count}` مقعد.\n"
                    if available_count > 0:
                        send_alert = True

            # ب) في حال الاعتماد على الفحص البصري للمكونات
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

            # --- الخطوة 4: إرسال التقرير عبر التليجرام ---
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
