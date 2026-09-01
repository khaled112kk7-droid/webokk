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

async def click_target_section(page, section_num):
    print(f"🎯 جاري محاولة الدخول والمشاهدة التفصيلية للمربع {section_num}...")
    
    # 1. البحث بالنص
    selectors = [
        f"text='{section_num}'",
        f"xpath=//*[text()='{section_num}']",
        f"xpath=//*[name()='text' or name()='tspan'][text()='{section_num}']"
    ]
    
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=2000):
                await loc.click(force=True)
                print(f"✅ تم النقر بواسطة المحدد: {sel}")
                await page.wait_for_timeout(3000)
                return True
        except Exception:
            pass

    # 2. النقر بالنص عبر الجافاسكربت وإطلاق أحدث mouseup/mousedown
    clicked = await page.evaluate(f"""(sec) => {{
        const elems = Array.from(document.querySelectorAll('*'));
        for (let el of elems) {{
            if (el.children.length === 0 && (el.textContent || '').trim() === sec) {{
                const target = el.closest('g') || el;
                target.scrollIntoView({{behavior: 'instant', block: 'center'}});
                
                ['mousedown', 'mouseup', 'click'].forEach(evtType => {{
                    target.dispatchEvent(new MouseEvent(evtType, {{
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }}));
                }});
                return true;
            }}
        }}
        return false;
    }}""", section_num)

    if clicked:
        print("✅ تم تنفيذ إشارات الضغط على المربع عبر JavaScript.")
        await page.wait_for_timeout(3000)
        return True

    # 3. إذا كان الـ Canvas يغطي المربع، النقر المباشر في منطقة المربع 525 (أعلى الخريطة الوسطى)
    try:
        canvas = page.locator("canvas#canvas, iframe[src*='seatcloud']").first
        if await canvas.is_visible(timeout=2000):
            box = await canvas.bounding_box()
            if box:
                # المربع 525 يقع تقريباً في الجزء العلوي الأوسط من الخريطة
                click_x = box['x'] + (box['width'] * 0.58)
                click_y = box['y'] + (box['height'] * 0.18)
                await page.mouse.click(click_x, click_y)
                print(f"🎯 تم النقر التقديري على موقع المربع 525 داخل Canvas ({click_x}, {click_y})")
                await page.wait_for_timeout(3000)
                return True
    except Exception as e:
        print(f"⚠️ فشل النقر المباشر عبر الكانفاس: {e}")

    return False

async def count_blue_interactive_seats(page):
    """فحص واحتساب المقاعد من شاشة العرض التفصيلية أو الـ API"""
    try:
        # فحص وجود كلمة 'انقر للاختيار' أو بيانات الصف والمقعد
        page_text = await page.evaluate("() => document.body.innerText || ''")
        
        if "انقر للاختيار" in page_text or "انقر لـ الاختيار" in page_text or "الصف" in page_text:
            return 1

        # فحص إضافي من داخل الـ Canvas / iframe
        iframe_text = await page.evaluate("""() => {
            let text = '';
            document.querySelectorAll('iframe').forEach(f => {
                try {
                    text += f.contentWindow.document.body.innerText || '';
                } catch(e) {}
            });
            return text;
        }""")

        if "30" in iframe_text or "انقر" in iframe_text:
            return 1

    except Exception as e:
        print(f"⚠️ تنبيه أثناء فحص المقاعد: {e}")

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

            # --- الانتظار حتى اكتمال تحميل الخريطة العامة ---
            print("⏳ الانتظار لاكتمال استقرار الخريطة...")
            await page.wait_for_timeout(4000)

            # --- الولوج والتعمق داخل المربع 525 ---
            await click_target_section(page, TARGET_SECTION)
            print("⏳ الانتظار 6 ثوانٍ لتطبيق التكبير وفتح خريطة التذاكر التفصيلية...")
            await page.wait_for_timeout(6000)

            # --- فحص المقاعد المتاحة ---
            print("🔍 جاري فحص واحتساب التذاكر والمقاعد الشاغرة...")
            
            blue_seats_count = await count_blue_interactive_seats(page)

            # تحليل استجابات الـ API الملتقطة من seatcloud/webook
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
                report += f"🟢 *الحالة:* تذاكر متاحة وموجودة! (انقر للإختيار)\n"
                report += f"🪑 *عدد المقاعد المتاحة:* `{total_available}` مقعد على الأقل.\n"
            else:
                report += f"🔴 *الحالة:* لم يتم التقاط مقاعد زرقاء في الوقت الحالي.\n"

            report += f"💵 *السعر:* `30 ﷼`"

            print(f"🎯 النتيجة المؤكدة للمربع {TARGET_SECTION}: {total_available} مقعد متاح.")

            # التقاط صورة الشاشة المباشرة وإرسالها
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
