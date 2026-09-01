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

# تحديد الفريق والمربع المستهدف
TARGET_TEAM = "الاتحاد"
TARGET_SECTION = "525"

seats_data_store = []
sections_status_store = {}
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
    global seats_data_store, sections_status_store, detected_sitekey
    url = response.url.lower()

    if "challenges.cloudflare.com" in url and "k=" in url:
        try:
            key = url.split("k=")[1].split("&")[0]
            if key and not key.startswith("6L"):
                detected_sitekey = key
        except Exception:
            pass

    # التقاط الـ API الخاص ببيانات القطاعات والمقاعد
    if any(k in url for k in ["seat", "map", "layout", "availability", "categories", "sections", "manifest", "event"]):
        try:
            if response.status == 200 and "json" in response.headers.get("content-type", ""):
                data = await response.json()
                
                if isinstance(data, dict):
                    sections = data.get("sections") or data.get("data", {}).get("sections") or []
                    for sec in sections:
                        sec_id = str(sec.get("name") or sec.get("id") or sec.get("section_code") or "")
                        if sec_id:
                            sections_status_store[sec_id] = sec

                    seats = data.get("seats") or data.get("data", {}).get("seats") or []
                    if seats:
                        seats_data_store.extend(seats)
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
    """إغلاق نافذة 'كيفية اختيار مقعد'"""
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
        print("✅ تم إغلاق النافذة بواسطة JavaScript بالنقر على 'حسناً'.")
        await page.wait_for_timeout(1000)
        return

    try:
        btn_okay = page.locator("text='حسناً'").first
        if await btn_okay.is_visible(timeout=2000):
            await btn_okay.click(force=True)
            print("✅ تم إغلاق النافذة عبر Playwright.")
            await page.wait_for_timeout(1000)
            return
    except Exception:
        pass

    try:
        await page.keyboard.press("Escape")
        print("⌨️ تم إرسال أمر Escape لإغلاق النافذة.")
    except Exception:
        pass

async def click_target_section(page, section_num):
    """النقر المباشر والدقيق على نص المربع في خريطة الـ SVG"""
    print(f"🎯 جاري محاولة الاستهداف والنقر المباشر على المربع {section_num}...")
    
    selector = f"xpath=//*[name()='text' or name()='tspan' or name()='g'][text()='{section_num}']"
    try:
        element = page.locator(selector).first
        if await element.is_visible(timeout=3000):
            await element.scroll_into_view_if_needed()
            await element.click(force=True)
            print(f"✅ تم النقر المباشر على المربع {section_num} عبر XPath.")
            return True
    except Exception as e:
        print(f"⚠️ لم نتمكن من النقر عبر XPath: {e}")

    clicked_js = await page.evaluate(f"""(sec) => {{
        const allTexts = Array.from(document.querySelectorAll('text, tspan, g, path, div'));
        for (let el of allTexts) {{
            if ((el.textContent || '').trim() === sec) {{
                const target = el.closest('g') || el;
                target.scrollIntoView({{behavior: 'instant', block: 'center'}});
                target.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
                target.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true }}));
                target.click();
                return true;
            }}
        }}
        return false;
    }}""", section_num)

    if clicked_js:
        print(f"✅ تم النقر على المربع {section_num} عبر JavaScript Event.")
        return True

    return False

async def count_available_seats_in_dom(page):
    """فحص المقاعد الشاغلة والمتاحة برمجياً من خريطة مقاعد المتصفح (DOM)"""
    return await page.evaluate("""() => {
        // البحث عن عناصر المقاعد الفردية داخل خريطة التذاكر (عادة تكون circle أو rect أو path داخل SVG)
        const seatSelectors = [
            'circle[data-seat-id]',
            'path[data-seat-id]',
            'g[data-seat]',
            'circle.seat',
            'circle[fill]:not([fill="none"])',
            'path[data-status]'
        ];

        let availableSeatsCount = 0;
        let totalDetected = 0;

        const allPotentialSeats = Array.from(document.querySelectorAll(seatSelectors.join(',')));

        allPotentialSeats.forEach(seat => {
            totalDetected++;
            const fill = (seat.getAttribute('fill') || '').toLowerCase();
            const stroke = (seat.getAttribute('stroke') || '').toLowerCase();
            const isUnavail = seat.classList.contains('disabled') || 
                              seat.classList.contains('sold') || 
                              seat.classList.contains('occupied') ||
                              seat.getAttribute('data-status') === 'sold' ||
                              seat.getAttribute('data-available') === 'false';

            // ألوان المقاعد غير المتاحة (عادة الرمادي أو الداكن)
            const unavailableFills = ['#2c2c2c', '#333333', '#1e1e1e', '#808080', '#cccccc', '#3a3a3c', 'gray'];

            const isGray = unavailableFills.some(c => fill.includes(c) || stroke.includes(c));

            if (!isUnavail && !isGray) {
                availableSeatsCount++;
            }
        });

        return {
            total: totalDetected,
            available: availableSeatsCount
        };
    }""")

async def run_monitor():
    global seats_data_store, sections_status_store, detected_sitekey
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

            # --- فحص حالة المربع 525 المباشرة قبل النقر ---
            print(f"🔍 [خطوة 10] فحص لون وحالة المربع {TARGET_SECTION} على الخريطة...")
            await page.wait_for_timeout(2000)

            section_state = await page.evaluate(f"""(sec) => {{
                const elements = Array.from(document.querySelectorAll('text, tspan, g, path'));
                for (let el of elements) {{
                    if ((el.textContent || '').trim() === sec) {{
                        const container = el.closest('g') || el;
                        const fill = container.getAttribute('fill') || el.getAttribute('fill') || '';
                        const isGray = fill === '#2c2c2c' || fill === '#333333' || fill === '#1e1e1e' || fill === '#808080';
                        return {{
                            found: true,
                            isClosed: isGray,
                            fillColor: fill
                        }};
                    }}
                }}
                return {{ found: false, isClosed: true, fillColor: 'none' }};
            }}""", TARGET_SECTION)

            # تنفيذ النقر المباشر والدقيق على المربع 525
            await click_target_section(page, TARGET_SECTION)
            print("⏳ الانتظار لتطبيق الزوم وفتح شبكة المقاعد التفصيلية...")
            await page.wait_for_timeout(4500)

            # --- فحص وحساب المقاعد المتاحة تفصيلياً ---
            print("🛈 [خطوة 11] بدء فحص المقاعد وحساب المتاح منها...")
            
            # 1. فحص المقاعد عبر الـ DOM المباشر في الشاشة
            dom_seat_stats = await count_available_seats_in_dom(page)
            dom_available_seats = dom_seat_stats.get("available", 0)

            # 2. فحص المقاعد المقتناصة عبر استجابات الـ API
            api_available_seats = 0
            if seats_data_store:
                section_525_seats = [
                    s for s in seats_data_store 
                    if str(s.get("section") or s.get("section_id") or s.get("sectionName") or s.get("block") or s.get("section_code") or "").strip() == TARGET_SECTION
                    and (s.get("status") in ["AVAILABLE", "available", "FREE", 1] or s.get("isAvailable") == True)
                ]
                api_available_seats = len(section_525_seats)

            # تحديد العدد النهائي المؤكد (الأعلى بين القراءتين لضمان عدم إغفال أي مقعد)
            final_available_count = max(dom_available_seats, api_available_seats)

            section_is_active = not section_state.get("isClosed", True)

            # بناء التقرير وإرساله
            report = "📊 *تقرير فحص وتعداد المقاعد المتاحة:*\n\n"
            report += f"🎟️ *المربع:* `{TARGET_SECTION}` (CAT 5)\n"
            
            if final_available_count > 0:
                report += f"🟢 *حالة القطاع:* متاح ومفتوح للحجز!\n"
                report += f"🪑 *عدد المقاعد المتاحة المؤكدة:* `{final_available_count}` مقعد\n"
            elif section_is_active:
                report += f"🟡 *حالة القطاع:* مفتوح ولكن جميع المقاعد محجوزة حالياً (`0` مقعد متاح)\n"
            else:
                report += f"🔴 *حالة القطاع:* مغلق من المنصة (Sold Out / Closed)\n"
                report += f"🪑 *عدد المقاعد المتاحة:* `0` مقعد\n"

            report += f"💵 *السعر التقديري:* `30 ﷼`"

            print(f"🎯 النتيجة النهائية: {final_available_count} مقعد متاح في القطاع {TARGET_SECTION}.")

            # --- التقاط صورة وإرسال التقرير للتليجرام ---
            try:
                await page.screenshot(path="completed_screenshot.png")
                send_telegram_photo("completed_screenshot.png", f"🏁 *حالة فحص المقاعد*\n\n{report}")
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
