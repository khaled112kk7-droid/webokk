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

# تحديد الفريق والمربع المستهدف
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

    # اقتناص الاستجابات الخاصة بالمقاعد والقطاعات
    if any(k in url for k in ["seat", "map", "layout", "availability", "categories", "sections", "manifest", "event"]):
        try:
            if response.status == 200 and "json" in response.headers.get("content-type", ""):
                data = await response.json()
                if isinstance(data, dict):
                    extracted = data.get("seats") or data.get("data") or data.get("categories") or data.get("sections") or data.get("manifest") or []
                    if extracted:
                        seats_data_store.append(data)
                elif isinstance(data, list):
                    seats_data_store.extend(data)
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
    """إغلاق نافذة التعليمات"""
    print("💡 جاري فحص نافذة التعليمات لمحاولة الإغلاق...")
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
        print("✅ تم إغلاق النافذة بواسطة JavaScript بالنقر على 'حسناً'.")
        await page.wait_for_timeout(1000)
        return

    try:
        btn_okay = page.locator("text='حسناً'").first
        if await btn_okay.is_visible(timeout=2000):
            await btn_okay.click(force=True)
            print("✅ تم إغلاق النافذة بالنقر على زر 'حسناً'.")
            await page.wait_for_timeout(1000)
            return
    except Exception:
        pass

    try:
        await page.keyboard.press("Escape")
        print("⌨️ تم إرسال أمر Escape لإغلاق النافذة.")
    except Exception:
        pass

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

                # --- 1. اختيار الفريق ---
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

                    # --- 2. تحديد مربع الشروط ---
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

            # --- الكابتشا ---
            print("⏳ [خطوة 8] جاري فحص الكابتشا...")
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
                print(f"⚠️ [خطوة 9] تم رصد الكابتشا (Sitekey: {detected_sitekey})! جاري الحل...")
                solved = await solve_turnstile_captcha(page, detected_sitekey)
                if solved:
                    print("✅ تم حل وتحقين توكن الكابتشا بنجاح!")

            # --- إغلاق نافذة التعليمات ---
            await close_instruction_modal(page)

            # --- النقر المحسّن للولوج للمربع 525 وتنشيط خريطة المقاعد ---
            print(f"🎯 [خطوة 10] النقر المباشر والدقيق على المربع {TARGET_SECTION}...")
            await page.wait_for_timeout(2000)

            # محاولة النقر الحقيقي عبر إحداثيات العنصر أو نص المربع 525
            click_success = await page.evaluate(f"""(sec) => {{
                // البحث عن أشكال أو نصوص تتضمن 525 داخل الخريطة التفاعلية
                const elements = Array.from(document.querySelectorAll('svg *, div, button, span'));
                for (let el of elements) {{
                    const txt = (el.textContent || '').trim();
                    if (txt === sec) {{
                        el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
                            el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true }}));
                            el.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""", TARGET_SECTION)

            if click_success:
                print(f"✅ تم النقر التفاعلي على المربع {TARGET_SECTION}.")
            else:
                print(f"⚠️ جاري المحاولة باستخدام النقر بالنقاط المركزية لخريطة الخيارات...")
                # نقر النواة المركزية المباشر لمركزي المربع 525
                await page.mouse.click(640, 400)

            await page.wait_for_timeout(4000)

            # --- قراءة واستخراج العدد المتاح للمقاعد ---
            print("📊 [خطوة 11] تحليل واستخراج مقاعد المربع 525...")
            
            count_525 = await page.evaluate(f"""(sec) => {{
                // 1. القراءة من واجهة القائمة الجانبية أو عناصر الشاشة المباشرة
                const pageText = document.body.innerText || '';
                
                // البحث عن عدد المقاعد المعروضة بالقرب من اسم المربع 525
                const lines = pageText.split('\\n');
                for (let i = 0; i < lines.length; i++) {{
                    if (lines[i].includes(sec) || lines[i].includes('525')) {{
                        for (let j = i; j < Math.min(i + 5, lines.length); j++) {{
                            const match = lines[j].match(/(\\d+)\\s*(مقعد|مقاعد|تذكرة|تذاكر|متوفر|متاح)/);
                            if (match) return parseInt(match[1]);
                        }}
                    }}
                }}

                // 2. حصر عناصر المقاعد الفردية المعروضة داخل خريطة SVG
                const svgSeats = document.querySelectorAll('svg circle, svg path[data-seat], svg rect[data-seat]');
                let availableCount = 0;
                svgSeats.forEach(s => {{
                    const fill = s.getAttribute('fill') || '';
                    const style = s.getAttribute('style') || '';
                    if (fill !== '#333333' && fill !== '#cccccc' && fill !== 'none' && !style.includes('gray')) {{
                        availableCount++;
                    }}
                }});

                return availableCount;
            }}""", TARGET_SECTION)

            # في حال استمرار القراءة 0، يتم فحص السجلات المقتناصة من الشبكة API
            if count_525 == 0 and seats_data_store:
                print("🔍 جاري التحقق النهائي في الاستجابات المستخرجة من الـ API...")
                for item in seats_data_store:
                    str_item = json.dumps(item)
                    if TARGET_SECTION in str_item:
                        # البحث عن قيم التوافر المباشرة
                        if "available" in str_item.lower():
                            count_525 += str_item.lower().count("available")

            report = "📊 *تقرير المقاعد المتاحة:*\n\n"
            report += f"🎟️ *تفاصيل المربع {TARGET_SECTION} (CAT 5):*\n"
            report += f"🔹 عدد المقاعد المتاحة: `{count_525}` مقعد.\n"
            report += f"💵 السعر: `30 ﷼`"

            print(f"🎯 النتيجة النهائية للمربع {TARGET_SECTION}: {count_525} مقعد متاح.")

            # --- التقاط صورة لنتيجة الفحص وإرسالها للتليجرام ---
            try:
                await page.screenshot(path="completed_screenshot.png")
                send_telegram_photo("completed_screenshot.png", f"🏁 *حالة خريطة المقاعد عند اكتمال الفحص*\n\n{report}")
            except Exception as img_err:
                print(f"⚠️ تعذر التقاط صورة الفحص: {img_err}")
                send_telegram(report)

        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع أثناء التنفيذ: {e}")
            try:
                await page.screenshot(path="error_screenshot.png")
                send_telegram_photo("error_screenshot.png", f"❌ توقف السكربت عند الخطأ التالي:\n`{e}`")
            except Exception as img_err:
                print(f"فشل التقاط أو إرسال الصورة: {img_err}")
        finally:
            print("🏁 إغلاق المتصفح وإنهاء السكربت.")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
