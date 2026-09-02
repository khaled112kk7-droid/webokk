import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

# استدعاء المتغيرات من البيئة (GitHub Secrets)
PHONE = os.getenv("WEBOOK_EMIL")
PASSWORD = os.getenv("WEBOOK_PASS")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")

EVENT_URL = "https://webook.com/ar/sa/jed/sports-event/events/rsl-al-ittihad-vs-al-nassr-050926/book"

TARGET_TEAM = "الاتحاد"
TARGET_SECTION = "525"

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

# --- البحث عن المربع 525 والتكبير عليه داخل الـ iframe ---
async def click_target_section(page, section_num):
    print(f"🎯 البحث عن المربع {section_num} داخل الـ iframe والنقر عليه...")
    await page.wait_for_timeout(3000)
    
    frame = page.frame(name="seats-iframe") or page.frame(url=lambda u: "seatcloud" in u)
    
    if not frame:
        for f in page.frames:
            if "seatcloud" in f.url or "chart" in f.url:
                frame = f
                break

    if frame:
        print("✅ تم العثور على إطار الخريطة الداخلي (iframe)!")
        canvas = frame.locator("canvas#canvas").first
        if await canvas.is_visible(timeout=5000):
            box = await canvas.bounding_box()
            if box:
                # إحداثيات موقع المربع 525 داخل الخريطة
                click_x = box['x'] + (box['width'] * 0.52)
                click_y = box['y'] + (box['height'] * 0.18)

                print(f"🖱️ النقر داخل الـ iframe على إحداثيات المربع {section_num}: ({click_x}, {click_y})")
                await page.mouse.click(click_x, click_y)
                await page.wait_for_timeout(1000)
                await page.mouse.click(click_x, click_y)
                await page.wait_for_timeout(4000)
                return True

    print("⚠️ تجربة النقر الاحتياطي المباشر...")
    await page.mouse.click(800, 220)
    await page.wait_for_timeout(3000)
    return True

# --- البحث عن التذاكر المتاحة بصفة خاصة لدرجة اللون rgb(59, 63, 98) ---
async def count_blue_interactive_seats(page):
    """فحص خريطة المقاعد بالألوان والبحث خصيصاً عن اللون المتاح rgb(59, 63, 98)"""
    print("🎨 جاري فحص ألوان المقاعد على الشاشة لدرجة اللون rgb(59, 63, 98)...")
    try:
        has_target_color = await page.evaluate("""() => {
            const iframe = document.querySelector('#seats-iframe') || document.querySelector('iframe');
            if (!iframe) return false;
            try {
                const canvas = iframe.contentWindow.document.querySelector('canvas#canvas');
                if (!canvas) return false;
                const ctx = canvas.getContext('2d');
                if (!ctx) return false;
                const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                
                for (let i = 0; i < imgData.length; i += 4) {
                    const r = imgData[i];
                    const g = imgData[i+1];
                    const b = imgData[i+2];
                    
                    // المطابقة لدرجة اللون الخاصة بالمقاعد المتاحة rgb(59, 63, 98)
                    if (Math.abs(r - 59) <= 10 && Math.abs(g - 63) <= 10 && Math.abs(b - 98) <= 10) {
                        return true;
                    }
                }
            } catch(e) {}
            return false;
        }""")
        if has_target_color:
            return 1
    except Exception as e:
        print(f"⚠️ تنبيه أثناء فحص ألوان المقاعد: {e}")

    return 0

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

                # --- 1. اختيار الفريق ---
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
                print(f"⚠️ تم رصد الكابتشا! جاري الحل...")
                await solve_turnstile_captcha(page, detected_sitekey)

            # --- إغلاق نافذة التعليمات ---
            await close_instruction_modal(page)

            print("⏳ الانتظار لاكتمال تحميل عناصر الخريطة...")
            await page.wait_for_timeout(4000)

            # --- الولوج للمربع 525 المباشر ---
            await click_target_section(page, TARGET_SECTION)
            print("⏳ الانتظار لتطبيق التكبير وفتح التذاكر التفصيلية...")
            await page.wait_for_timeout(6000)

            # --- فحص المقاعد المتاحة ---
            print("🔍 جاري فحص واحتساب التذاكر والمقاعد الشاغرة...")
            
            blue_seats_count = await count_blue_interactive_seats(page)

            api_seats_count = 0
            if seats_data_store:
                for item in seats_data_store:
                    raw_str = json.dumps(item.get("data", {}))
                    if "525" in raw_str and ("AVAILABLE" in raw_str or "available" in raw_str or "free" in raw_str):
                        count = raw_str.count("AVAILABLE") + raw_str.count('"status":"available"')
                        if count > api_seats_count:
                            api_seats_count = count

            total_available = max(blue_seats_count, api_seats_count)

            report = "📊 *تقرير المقاعد المتاحة بالمعاينة المباشرة:*\n\n"
            report += f"🎟️ *المربع:* `{TARGET_SECTION}` (CAT 5)\n"
            
            if total_available > 0:
                report += f"🟢 *الحالة:* تم التقاط درجة اللون المتاحة `rgb(59, 63, 98)` في الخريطة! 🎉\n"
            else:
                report += f"🔴 *الحالة:* لم يتم التقاط مقاعد بدرجة اللون المحددة في الوقت الحالي.\n"

            report += f"💵 *السعر:* `30 ﷼`"

            print(f"🎯 النتيجة المؤكدة للمربع {TARGET_SECTION}: {total_available} مقعد متاح.")

            try:
                await page.screenshot(path="completed_screenshot.png")
                send_telegram_photo("completed_screenshot.png", f"🏁 *نتائج فحص المربع {TARGET_SECTION}*\n\n{report}")
            except Exception as img_err:
                print(f"⚠️ تعذر التقاط الصورة: {img_err}")
                send_telegram(report)

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
