import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

# استدعاء المتغيرات من البيئة
PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")

EVENT_URL = "https://webook.com/ar/sa/jed/sports-event/events/rsl-al-ittihad-vs-al-nassr-050926/book"
TARGET_CATEGORIES = ["Premium", "Premium 2"]

# اسم الفريق المطلوب تحديده ("الاتحاد" أو "النصر")
TARGET_TEAM = "الاتحاد"

seats_data_store = []
detected_sitekey = None

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ فشل إرسال التنبيه عبر التليجرام: {e}")

def send_telegram_photo(photo_path, caption="📸 صورة من السكربت"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            files = {"photo": photo}
            requests.post(url, data=payload, files=files, timeout=15)
            print("📬 تم إرسال الصورة إلى التليجرام بنجاح!")
    except Exception as e:
        print(f"❌ فشل إرسال الصورة عبر التليجرام: {e}")

async def solve_turnstile_captcha(page, sitekey):
    if not CAPTCHA_API_KEY:
        print("⚠️ لم يتم ضبط CAPTCHA_API_KEY في GitHub Secrets.")
        return False

    method = "turnstile"
    if str(sitekey).startswith("6L"):
        method = "userrecaptcha"

    print(f"🧩 جاري إرسال الكابتشا لخدمة 2Captcha (Method: {method}, Sitekey: {sitekey})...")
    
    if method == "turnstile":
        req_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method=turnstile&sitekey={sitekey}&pageurl={page.url}&json=1"
    else:
        req_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method=userrecaptcha&googlekey={sitekey}&pageurl={page.url}&json=1"

    try:
        res = requests.get(req_url).json()
        if res.get("status") != 1:
            print(f"❌ فشل إرسال الكابتشا: {res.get('request')}")
            return False

        request_id = res.get("request")
        fetch_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={request_id}&json=1"

        for _ in range(35):
            await asyncio.sleep(4)
            sol_res = requests.get(fetch_url).json()
            if sol_res.get("status") == 1:
                token = sol_res.get("request")
                print("✅ تم استلام توكن الكابتشا بنجاح! جاري تحقينه بالصفحة...")
                
                await page.evaluate(f"""(token) => {{
                    const inputs = document.querySelectorAll('input[name*="turnstile"], input[name*="g-recaptcha"], [name="cf-turnstile-response"]');
                    inputs.forEach(i => i.value = token);
                    if (window.turnstile) {{
                        try {{ turnstile.render(); }} catch(e) {{}}
                    }}
                }}""", token)
                await page.wait_for_timeout(2000)
                return True

        print("⏰ انتهت مهلة حل الكابتشا.")
        return False
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بـ 2Captcha: {e}")
        return False

async def handle_response(response):
    global seats_data_store, detected_sitekey
    url = response.url.lower()

    if "challenges.cloudflare.com" in url and "k=" in url:
        try:
            key = url.split("k=")[1].split("&")[0]
            if key and not key.startswith("6L"):
                detected_sitekey = key
        except Exception:
            pass

    if any(k in url for k in ["seat", "map", "layout", "availability", "categories", "sections"]):
        try:
            if response.status == 200 and "json" in response.headers.get("content-type", ""):
                data = await response.json()
                if isinstance(data, dict):
                    extracted = data.get("seats") or data.get("data") or data.get("categories") or data.get("sections") or []
                    if extracted:
                        seats_data_store = extracted
                elif isinstance(data, list):
                    seats_data_store = data
        except Exception:
            pass

async def close_cookie_banner(page):
    try:
        cookie_btn = page.locator("button:has-text('قبول الكل'), button:has-text('رفض الكل الغير ضروري')").first
        if await cookie_btn.is_visible(timeout=3000):
            await cookie_btn.click(force=True)
            print("🍪 تم إغلاق إشعار الكوكيز.")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def run_monitor():
    global seats_data_store, detected_sitekey
    async with async_playwright() as p:
        print("🚀 بدء تشغيل المتصفح...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        page.on("response", handle_response)

        try:
            print("🌐 [خطوة 1] الانتقال لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="networkidle")
            print("✅ تم فتح الصفحة بنجاح.")
            
            await close_cookie_banner(page)

            # --- تسجيل الدخول ---
            email_input = page.locator("input[type='email'], input[placeholder*='you@email.com']").first
            if await email_input.is_visible(timeout=5000):
                print("📧 [خطوة 2] إدخال البريد الإلكتروني...")
                await email_input.fill(str(PHONE))
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
                print("✅ [خطوة 4] تم تسجيل الدخول بنجاح!")

                # --- 1. اختيار الشعار/الفريق (مرن) ---
                print(f"⚽ [خطوة 5] جاري الفحص لاختيار بطاقة فريق ({TARGET_TEAM})...")
                await page.wait_for_timeout(1500)

                clicked = await page.evaluate(f"""(teamName) => {{
                    const interactiveElements = Array.from(document.querySelectorAll('button, div[role="button"], a, div'));
                    
                    for (let el of interactiveElements) {{
                        const text = el.innerText || '';
                        const alt = el.getAttribute('alt') || '';
                        
                        if ((text.trim() === teamName || alt === teamName) && el.children.length < 5) {{
                            const clickable = el.closest('button') || el;
                            clickable.scrollIntoView({{behavior: 'instant', block: 'center'}});
                            clickable.click();
                            return true;
                        }}
                    }}
                    return false;
                }}""", TARGET_TEAM)

                if not clicked:
                    img_locator = page.locator(f"img[alt='{TARGET_TEAM}']").first
                    if await img_locator.is_visible(timeout=2000):
                        await img_locator.click(force=True)
                        clicked = True

                if clicked:
                    print(f"✅ تم تحديد فريق ({TARGET_TEAM}) بنجاح.")
                    await page.wait_for_timeout(1500)

                    # --- 2. تحديد مربع أوافق (Checkbox) ---
                    print("☑️ [خطوة 6] تحديد مربع الشروط (Checkbox)...")
                    checkbox = page.locator("input[type='checkbox'], [role='checkbox']").first
                    if await checkbox.is_visible(timeout=3000):
                        if not await checkbox.is_checked():
                            await checkbox.check(force=True)
                            print("✅ تم تفعيل مربع الموافقة.")
                    await page.wait_for_timeout(1000)

                    # --- 3. النقر على زر التالي ---
                    print("➡️ [خطوة 7] النقر على زر (التالي / اختيار التذاكر)...")
                    next_btn = page.locator("button:has-text('التالي'), button:has-text('اختيار التذاكر')").first
                    if await next_btn.is_visible(timeout=3000):
                        await next_btn.click(force=True)
                        print("✅ تم التجاوز والنقر على زر التالي بنجاح.")
                else:
                    print("ℹ️ لم تُظهر الصفحة واجهة اختيار الفريق، الانتقال المباشر للخطوة 8...")

            # --- الكابتشا تظهر في الخطوة 8 ---
            print("⏳ [خطوة 8] جاري فحص واكتشاف وجود كابتشا Cloudflare الآن...")
            for _ in range(8):
                await page.wait_for_timeout(1000)
                if not detected_sitekey:
                    detected_sitekey = await page.evaluate("""() => {
                        const cfEl = document.querySelector('.cf-turnstile, [data-sitekey]');
                        if (cfEl && cfEl.getAttribute('data-sitekey')) return cfEl.getAttribute('data-sitekey');
                        
                        const iframes = Array.from(document.querySelectorAll('iframe'));
                        for (let iframe of iframes) {
                            if (iframe.src.includes('challenges.cloudflare.com') || iframe.src.includes('turnstile')) {
                                const match = iframe.src.match(/k=([^&]+)/) || iframe.src.match(/sitekey=([^&]+)/);
                                if (match) return match[1];
                            }
                        }
                        return null;
                    }""")
                if detected_sitekey:
                    break

            if detected_sitekey:
                print(f"⚠️ [خطوة 9] تم رصد الكابتشا (Sitekey: {detected_sitekey})! جاري إرسالها للحل...")
                solved = await solve_turnstile_captcha(page, detected_sitekey)
                if solved:
                    print("✅ تم حل وتحقين توكن الكابتشا بنجاح!")
            else:
                print("ℹ️ لم تُظهر الصفحة أي كابتشا، جاري التوجه مباشرة لخريطة المقاعد...")

            # --- استخراج البيانات والتنبيه ---
            print("⏳ [خطوة 10] انتظار فتح خريطة المقاعد وقراءة الـ API...")
            await page.wait_for_timeout(10000)

            report = "📊 *تقرير المقاعد المتاحة:*\n\n"
            send_alert = False

            if seats_data_store:
                print(f"✅ تم اقتناص {len(seats_data_store)} عنصر مقاعد من الـ API مباشرة!")
                for category in TARGET_CATEGORIES:
                    available_count = len([
                        s for s in seats_data_store 
                        if (s.get("status") in ["AVAILABLE", "available", "FREE", 1] or s.get("isAvailable") == True) 
                        and category.lower() in str(s.get("category") or s.get("name") or s.get("title") or "").lower()
                    ])
                    
                    report += f"🔹 *{category}:* متبقي `{available_count}` مقعد.\n"
                    if available_count > 0:
                        send_alert = True
            else:
                print("🔍 لم يتم اقتناص API المقاعد، جاري فحص نصوص الصفحة مباشرة...")
                page_text = await page.content()
                for category in TARGET_CATEGORIES:
                    if category in page_text:
                        report += f"✅ *{category}:* متاحة الآن للحجز!\n"
                        send_alert = True
                    else:
                        report += f"❌ *{category}:* غير متاحة أو نفدت.\n"

            # --- التقاط صورة لنتيجة الفحص المكتمل وإرسالها للتليجرام ---
            try:
                await page.screenshot(path="completed_screenshot.png")
                send_telegram_photo("completed_screenshot.png", f"🏁 *حالة خريطة المقاعد عند اكتمال الفحص*\n\n{report}")
            except Exception as img_err:
                print(f"⚠️ تعذر التقاط صورة الفحص المكتمل: {img_err}")
                if send_alert:
                    send_telegram(report)

        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع أثناء التنفيذ: {e}")
            try:
                await page.screenshot(path="error_screenshot.png")
                print("📸 تم حفظ صورة لمكان التوقف: error_screenshot.png")
                send_telegram_photo("error_screenshot.png", f"❌ توقف السكربت عند الخطأ التالي:\n`{e}`")
            except Exception as img_err:
                print(f"فشل التقاط أو إرسال الصورة: {img_err}")
        finally:
            print("🏁 إغلاق المتصفح وإنهاء السكربت.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
