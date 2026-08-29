import os
import re
import requests
from playwright.sync_api import sync_playwright

# ==========================================
# 1. قراءة البيانات الحساسة من GitHub Secrets
# ==========================================
WEBOOK_EMAIL = os.getenv("WEBOOK_EMAIL")
WEBOOK_PASSWORD = os.getenv("WEBOOK_PASSWORD")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROXY_SERVER = os.getenv("PROXY_SERVER")  # http://geo.iproyal.com:11200
PROXY_USER = os.getenv("PROXY_USER")      # QCuwByHUpvHD482R
PROXY_PASS = os.getenv("PROXY_PASS")      # الباسورد الكامل من IPRoyal

EVENT_URL = "https://webook.com/ar/sa/jed/sports-event/events/rsl-al-ittihad-vs-al-nassr-050926/book"

def send_telegram_alert(tickets_count):
    """إرسال إشعار التنبيه إلى بوت تليجرام"""
    message = (
        f"⚠️ **تنبيه تذاكر Webook!**\n\n"
        f"🚨 المربع **121** متبقي فيه **{tickets_count}** مقاعد فقط!\n"
        f"🔗 [اضغط هنا للحجز فوراً]({EVENT_URL})"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("تم إرسال التنبيه عبر تليجرام بنجاح!")
    except Exception as e:
        print(f"خطأ في إرسال التنبيه لتليجرام: {e}")

def check_section_121():
    with sync_playwright() as p:
        # إعدادات البروكسي السكني من IPRoyal
        launch_options = {"headless": True}
        
        if PROXY_SERVER:
            launch_options["proxy"] = {
                "server": PROXY_SERVER,
                "username": PROXY_USER if PROXY_USER else "",
                "password": PROXY_PASS if PROXY_PASS else ""
            }

        print("بدء تشغيل المتصفح عبر البروكسي السكني...")
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context()
        page = context.new_page()

        try:
            # --------------------------------------------------
            # الخطوة الأولى: الانتقال وقبول الكوكيز
            # --------------------------------------------------
            page.goto("https://webook.com/ar/login", wait_until="networkidle")
            try:
                cookie_btn = page.locator('button:has-text("قبول الكل")')
                if cookie_btn.is_visible(timeout=5000):
                    cookie_btn.click()
                    print("1. تم قبول الكوكيز.")
                    page.wait_for_timeout(1000)
            except Exception as e:
                print("تجاوز خطوة الكوكيز:", e)

            # --------------------------------------------------
            # الخطوة الثانية والثالثة: البريد وكلمة المرور
            # --------------------------------------------------
            if page.locator('input[type="email"]').is_visible(timeout=4000):
                page.fill('input[type="email"]', WEBOOK_EMAIL)
                print("2. تم كتابة البريد الإلكتروني.")
                page.fill('input[type="password"]', WEBOOK_PASSWORD)
                print("3. تم كتابة كلمة المرور.")
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle")

            # --------------------------------------------------
            # الخطوة الرابعة: اختيار شعار الاتحاد
            # --------------------------------------------------
            page.goto(EVENT_URL, wait_until="networkidle")
            try:
                ittihad_btn = page.locator('img[alt*="الاتحاد"], [data-team*="ittihad"], text="الاتحاد"').first
                if ittihad_btn.is_visible(timeout=8000):
                    ittihad_btn.click()
                    print("4. تم اختيار شعار الاتحاد.")
                    page.wait_for_timeout(2000)
            except Exception as e:
                print("تجاوز خطوة شعار الاتحاد:", e)

            # --------------------------------------------------
            # الخطوة الخامسة: إغلاق نافذة "كيفية اختيار مقعد" (حسناً)
            # --------------------------------------------------
            try:
                got_it_btn = page.locator('button:has-text("حسناً"), button:has-text("حسنا")')
                if got_it_btn.is_visible(timeout=6000):
                    got_it_btn.click()
                    print("5. تم الضغط على زر (حسناً) وإغلاق النافذة.")
                    page.wait_for_timeout(1500)
            except Exception as e:
                print("تجاوز نافذة التعليمات:", e)

            # --------------------------------------------------
            # الخطوة السادسة: النقر على المربع 121 وقراءة المقاعد
            # --------------------------------------------------
            print("6. البحث عن المربع 121 على الخريطة...")
            section_121 = page.locator('text="121"').first
            section_121.wait_for(state="visible", timeout=10000)
            section_121.click()
            print("تم النقر على المربع 121.")
            page.wait_for_timeout(2000)

            # قراءة النصوص لاستخراج العدد
            info_text = page.locator('body').inner_text()

            if "لا توجد مقاعد" in info_text:
                tickets_count = 0
            else:
                numbers = re.findall(r'(\d+)\s*(تذاكر|تذكرة|مقاعد|مقعد|tickets|seats)', info_text, re.IGNORECASE)
                tickets_count = int(numbers[0][0]) if numbers else 0

            print(f"نتيجة الفحص: عدد المقاعد المتاحة في المربع 121 هو: {tickets_count}")

            # الشرط: إذا المتبقي 10 أو أقل (وأكبر من 0)
            if 0 < tickets_count <= 10:
                send_telegram_alert(tickets_count)
            elif tickets_count > 10:
                print(f"التذاكر متوفرة بكثرة ({tickets_count} مقعد).")
            else:
                print("المربع 121 غير متاح حالياً.")

        except Exception as e:
            print(f"حدث خطأ أثناء تنفيذ السكربت: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    check_section_121()
