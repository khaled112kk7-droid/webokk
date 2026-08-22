import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")

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

async def solve_turnstile_captcha(page, sitekey):
    """حل كابتشا Turnstile وإرسال الـ Token مباشرة إلى الصفحة"""
    if not CAPTCHA_API_KEY:
        print("⚠️ لم يتم ضبط CAPTCHA_API_KEY في GitHub Secrets.")
        return False

    print("🧩 جاري إرسال الكابتشا لخدمة 2Captcha للحل...")
    req_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method=turnstile&sitekey={sitekey}&pageurl={page.url}&json=1"
    res = requests.get(req_url).json()

    if res.get("status") != 1:
        print(f"❌ فشل إرسال الكابتشا: {res.get('request')}")
        return False

    request_id = res.get("request")
    fetch_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={request_id}&json=1"

    for _ in range(30):
        await asyncio.sleep(4)
        sol_res = requests.get(fetch_url).json()
        if sol_res.get("status") == 1:
            token = sol_res.get("request")
            print("✅ تم استلام توكن الكابتشا! جاري تحقينه واستدعاء التجاوز...")
            
            # تحقين توكن الحل في نموذج الكابتشا
            await page.evaluate(f"""(token) => {{
                const input = document.querySelector('input[name="cf-turnstile-response"]') || document.querySelector('[name="g-recaptcha-response"]');
                if (input) {{ input.value = token; }}
                if (window.turnstile) {{
                    try {{ turnstile.render(); }} catch(e) {{}}
                }}
            }}""", token)
            await page.wait_for_timeout(2000)
            return True

    print("⏰ انتهت مهلة حل الكابتشا.")
    return False

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

        page.on("response", handle_response)

        try:
            print("الانتقال المباشر لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="networkidle")
            await close_cookie_banner(page)

            # تسجيل الدخول
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
                print("تم تسجيل الدخول بنجاح!")

                await close_cookie_banner(page)

                # اختيار الفريق والموافقة
                print("جاري النقر على (الهلال)...")
                await page.evaluate("""() => {
                    const pElements = Array.from(document.querySelectorAll('p'));
                    const hilalP = pElements.find(el => el.textContent.trim() === 'الهلال');
                    if (hilalP) {
                        const button = hilalP.closest('button');
                        if (button) button.click();
                        else hilalP.click();
                    }
                }""")
                await page.wait_for_timeout(1500)

                print("جاري النقر على مربع الموافقة...")
                await page.evaluate("""() => {
                    const labels = Array.from(document.querySelectorAll('label, span, div, p'));
                    const agreeEl = labels.find(el => el.textContent.includes('أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط'));
                    if (agreeEl) agreeEl.click();
                }""")
                await page.wait_for_timeout(1500)

                # Step: الضغط على زر (التالي: اختيار التذاكر)
                print("جاري النقر على زر (التالي: اختيار التذاكر)...")
                await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const nextBtn = buttons.find(btn => btn.textContent.includes('التالي: اختيار التذاكر') || btn.textContent.includes('اختيار التذاكر'));
                    if (nextBtn) nextBtn.click();
                }""")
                print("✅ تم الضغط على (التالي: اختيار التذاكر).")

            # Step: التعامل المباشر مع الكابتشا التي تظهر فوراً بعد الزر
            await page.wait_for_timeout(3000)
            
            # البحث عن وجود الكابتشا
            sitekey = await page.evaluate("""() => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : null;
            }""")

            if sitekey:
                print(f"⚠️ ظهرت الكابتشا بعد اختيار التذاكر (Sitekey: {sitekey})! جاري الحل...")
                solved = await solve_turnstile_captcha(page, sitekey)
                
                if solved:
                    print("✅ تم حل الكابتشا، جاري إعادة ضغط (التالي) لفتح خريطة المقاعد...")
                    await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const nextBtn = buttons.find(btn => btn.textContent.includes('التالي: اختيار التذاكر') || btn.textContent.includes('اختيار التذاكر'));
                        if (nextBtn) nextBtn.click();
                    }""")

            # الانتظار الكامل لاكتمال تحويل الصفحة وفتح خريطة المقاعد
            print("⏳ جاري انتظار تحميل خريطة المقاعد...")
            await page.wait_for_timeout(8000)

            # Step: التقرير وفحص المقاعد بعد فتح الخريطة
            report = "📊 *تقرير المقاعد المتاحة (الهلال ضد الشباب):*\n\n"
            send_alert = False

            if seats_data_store:
                print("✅ تم فتح الخريطة واستخراج البيانات بنجاح عبر الـ API!")
                for category in TARGET_CATEGORIES:
                    available_count = len([
                        s for s in seats_data_store 
                        if s.get("status") == "AVAILABLE" and category.lower() in str(s.get("category", "")).lower()
                    ])
                    report += f"🔹 *{category}:* متبقي `{available_count}` مقعد.\n"
                    if available_count > 0:
                        send_alert = True
            else:
                print("🔍 جاري فحص عناصر الصفحة مباشرة...")
                page_text = await page.content()
                for category in TARGET_CATEGORIES:
                    if category in page_text:
                        report += f"✅ *{category}:* متاحة الآن للحجز!\n"
                        send_alert = True
                    else:
                        report += f"❌ *{category}:* غير متاحة أو نفدت.\n"

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
