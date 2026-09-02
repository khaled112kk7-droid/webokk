import os
import io
import asyncio
import requests
from PIL import Image
import pytesseract
from playwright.async_api import async_playwright

# استدعاء المتغيرات من البيئة (GitHub Secrets)
PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")

# رابط المباراة الجديد
EVENT_URL = "https://webook.com/ar/sa/jed/sports-event/events/rsl-al-ittihad-vs-al-nassr-050926/book"
TARGET_TEAM = "الاتحاد"

# ألوان النفاد المطلوبة حصراً (30, 30, 30) و (34, 34, 34)
SOLD_OUT_COLORS = [(30, 30, 30), (34, 34, 34)]
TARGET_NUMBERS = ["525", "322", "323"]

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

    if any(k in url for k in ["seatcloud.com", "seats", "map", "availability", "categories", "sections", "manifest", "event", "chart"]):
        try:
            if response.status == 200 and "json" in response.headers.get("content-type", ""):
                data = await response.json()
                if isinstance(data, dict) or isinstance(data, list):
                    seats_data_store.append({"url": url, "data": data})
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

async def close_instruction_modal(page):
    print("💡 جاري فحص وإغلاق نافذة التعليمات...")
    await page.wait_for_timeout(2500)

    closed_via_js = await page.evaluate("""() => {
        const elements = Array.from(document.querySelectorAll('button, div, span, a'));
        for (let el of elements) {
            const txt = (el.innerText || '').trim();
            if (txt === 'حسناً' || txt === 'حسنا' || txt === 'Got it' || txt === 'OK') {
                el.click();
                return true;
            }
        }
        return false;
    }""")

    if closed_via_js:
        print("✅ تم إغلاق النافذة بالنقر على 'حسناً'.")
        await page.wait_for_timeout(1000)
        return

    try:
        btn_okay = page.locator("text='حسناً'").first
        if await btn_okay.is_visible(timeout=2000):
            await btn_okay.click(force=True)
            await page.wait_for_timeout(1000)
            return
    except Exception:
        pass

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

# --- دالة الفحص البصري لمربعات الأرقام المحددة بحثاً عن الألوان (30,30,30) و (34,34,34) ---
async def check_sold_out_status(page):
    print(f"🔍 جاري البحث عن مواقع الأرقام: {TARGET_NUMBERS} وفحص مربعاتها الخاصة...")
    await page.wait_for_timeout(3000)

    frame = page.frame(name="seats-iframe") or page.frame(url=lambda u: "seatcloud" in u or "seats" in u)
    if not frame:
        for f in page.frames:
            if "seatcloud" in f.url or "index.html" in f.url:
                frame = f
                break

    target = frame if frame else page

    canvas_elem = await target.query_selector('canvas#canvas, canvas')
    if not canvas_elem:
        print("⚠️ لم يتم العثور على عنصر Canvas داخل الخريطة.")
        return {}

    screenshot_bytes = await canvas_elem.screenshot()
    img = Image.open(io.BytesIO(screenshot_bytes)).convert('RGB')
    
    ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    results = {}

    for num in TARGET_NUMBERS:
        found_num = False
        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            if text == num:
                found_num = True
                x, y, w, h = ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i]

                # قص المربع حول الرقم مع هامش 15 بكسل
                padding = 15
                crop_box = (
                    max(0, x - padding),
                    max(0, y - padding),
                    min(img.width, x + w + padding),
                    min(img.height, y + h + padding)
                )

                cropped_img = img.crop(crop_box)
                cw, ch = cropped_img.size

                grey_pixels = 0
                for cx in range(cw):
                    for cy in range(ch):
                        pixel = cropped_img.getpixel((cx, cy))
                        if pixel in SOLD_OUT_COLORS:
                            grey_pixels += 1

                # وجود أكثر من 10 بكسلات يثبت أن المربع مغلق/نفذت التذاكر
                is_sold_out = grey_pixels > 10
                print(f"📌 الرقم {num}: الموقع ({x},{y}) | بكسلات اللون الرمادي المغلق: {grey_pixels} | الحالة: {'نفذت 🔴' if is_sold_out else 'متاح 🟢'}")
                results[num] = {"found": True, "sold_out": is_sold_out, "grey_pixels": grey_pixels}
                break

        if not found_num:
            print(f"⚠️ لم يتم التعرف على موقع الرقم {num} بـ OCR.")
            results[num] = {"found": False, "sold_out": False, "grey_pixels": 0}

    return results

async def run_monitor():
    global seats_data_store, detected_sitekey
    async with async_playwright() as p:
        print("🚀 بدء تشغيل المتصفح...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        page.on("response", handle_response)

        try:
            print("🌐 [خطوة 1] الانتقال لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="networkidle")
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

                # --- اختيار الفريق ---
                print(f"⚽ [خطوة 4] جاري اختيار فريق ({TARGET_TEAM})...")
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

                if clicked:
                    await page.wait_for_timeout(1500)
                    checkbox = page.locator("input[type='checkbox'], [role='checkbox']").first
                    if await checkbox.is_visible(timeout=3000):
                        if not await checkbox.is_checked():
                            await checkbox.check(force=True)
                    await page.wait_for_timeout(1000)

                    next_btn = page.locator("button:has-text('التالي'), button:has-text('اختيار التذاكر')").first
                    if await next_btn.is_visible(timeout=3000):
                        await next_btn.click(force=True)

            # --- الكابتشا ---
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
                print("⚠️ تم رصد الكابتشا! جاري الحل...")
                await solve_turnstile_captcha(page, detected_sitekey)

            # --- إغلاق نافذة التعليمات ---
            await close_instruction_modal(page)

            print("⏳ الانتظار لاكتمال تحميل الخريطة...")
            await page.wait_for_timeout(4000)

            await page.screenshot(path="completed_screenshot.png")
            
            scan_results = await check_sold_out_status(page)

            report_lines = []
            any_available = False

            for num in TARGET_NUMBERS:
                res = scan_results.get(num, {})
                if not res.get("found"):
                    report_lines.append(f"❓ المربع `{num}`: لم يتم التعرف على موقع الرقم")
                elif res.get("sold_out"):
                    report_lines.append(f"🔴 المربع `{num}`: *نفذت التذاكر (رمادي مغلق)*")
                else:
                    report_lines.append(f"🟢 المربع `{num}`: **ملون ومتاح!** 🎉")
                    any_available = True

            report_text = "\n".join(report_lines)
            if any_available:
                full_report = f"🔔 *تنبيه توفر تذاكر!*\n\n{report_text}"
            else:
                full_report = f"📊 *تقرير فحص حالة المربعات المطلوبة:*\n\n{report_text}"

            send_telegram_photo("completed_screenshot.png", f"🏁 *نتيجة فحص الخريطة*\n\n{full_report}")

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
