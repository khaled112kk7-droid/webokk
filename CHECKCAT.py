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

EVENT_URL = "https://webook.com/ar/sa/jed/sports-event/events/rsl-al-ittihad-vs-al-nassr-050926/book"
TARGET_TEAM = "الاتحاد"
TARGET_SECTION = "525"

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
        return False
    method = "turnstile" if not str(sitekey).startswith("6L") else "userrecaptcha"
    req_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method={method}&sitekey={sitekey}&pageurl={page.url}&json=1"

    try:
        res = requests.get(req_url).json()
        if res.get("status") != 1: return False
        request_id = res.get("request")
        fetch_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={request_id}&json=1"

        for _ in range(35):
            await asyncio.sleep(4)
            sol_res = requests.get(fetch_url).json()
            if sol_res.get("status") == 1:
                token = sol_res.get("request")
                await page.evaluate(f"""(token) => {{
                    const inputs = document.querySelectorAll('input[name*="turnstile"], input[name*="g-recaptcha"], [name="cf-turnstile-response"]');
                    inputs.forEach(i => i.value = token);
                }}""", token)
                await page.wait_for_timeout(2000)
                return True
        return False
    except Exception:
        return False

async def close_cookie_and_modal(page):
    try:
        cookie_btn = page.locator("button:has-text('قبول الكل')").first
        if await cookie_btn.is_visible(timeout=2000):
            await cookie_btn.click(force=True)
    except Exception:
        pass

    try:
        btn_okay = page.locator("text='حسناً'").first
        if await btn_okay.is_visible(timeout=2000):
            await btn_okay.click(force=True)
    except Exception:
        pass

async def click_section_inside_iframe(page):
    print("🎯 جاري البحث عن الخريطة داخل iframe وسحب العنصر...")
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
                click_x = box['x'] + (box['width'] * 0.52)
                click_y = box['y'] + (box['height'] * 0.18)

                print(f"🖱️ النقر داخل الـ iframe على إحداثيات المربع 525: ({click_x}, {click_y})")
                await page.mouse.click(click_x, click_y)
                await page.wait_for_timeout(1000)
                await page.mouse.click(click_x, click_y)
                await page.wait_for_timeout(4000)
                return True

    print("⚠️ جاري تجربة النقر الاحتياطي عبر الإحداثيات المباشرة...")
    await page.mouse.click(800, 220)
    await page.wait_for_timeout(3000)
    return True

async def inspect_blue_pixels(page):
    """فحص خريطة المقاعد بالألوان والبحث خصيصاً عن اللون المتاح rgb(59, 63, 98)"""
    print("🎨 جاري فحص ألوان المقاعد على الشاشة لدرجة اللون rgb(59, 63, 98)...")
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
                
                // مطابقة درجة اللون الخاصة بالتذاكر المتاحة rgb(59, 63, 98)
                if (Math.abs(r - 59) <= 10 && Math.abs(g - 63) <= 10 && Math.abs(b - 98) <= 10) {
                    return true;
                }
            }
        } catch(e) {}
        return false;
    }""")
    return has_target_color

async def run_monitor():
    async with async_playwright() as p:
        print("🚀 بدء تشغيل المتصفح...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        try:
            print("🌐 [1] الانتقال لصفحة الفعالية...")
            await page.goto(EVENT_URL, wait_until="networkidle")
            await close_cookie_and_modal(page)

            # --- تسجيل الدخول ---
            email_input = page.locator("input[type='email']").first
            if await email_input.is_visible(timeout=4000):
                print("📧 [2] إدخال البريد الإلكتروني...")
                await email_input.fill(str(PHONE))
                await email_input.press("Enter")

                password_input = page.locator("input[type='password']").first
                await password_input.wait_for(timeout=10000)
                print("🔑 [3] إدخال كلمة المرور...")
                await password_input.fill(str(PASSWORD))
                await password_input.press("Enter")
                await page.wait_for_timeout(4000)

                # --- اختيار الفريق ---
                print(f"⚽ [4] اختيار فريق {TARGET_TEAM}...")
                await page.evaluate(f"""(team) => {{
                    const els = Array.from(document.querySelectorAll('button, div, a'));
                    for (let el of els) {{
                        if ((el.innerText || '').trim() === team) {{
                            el.click();
                            break;
                        }}
                    }}
                }}""", TARGET_TEAM)
                await page.wait_for_timeout(1500)

                next_btn = page.locator("button:has-text('التالي'), button:has-text('اختيار التذاكر')").first
                if await next_btn.is_visible(timeout=3000):
                    await next_btn.click(force=True)

            await close_cookie_and_modal(page)
            await page.wait_for_timeout(3000)

            # --- النقر على المربع 525 داخل الـ iframe ---
            await click_section_inside_iframe(page)

            # --- فحص الألوان للمقاعد المتاحة ---
            is_seats_available = await inspect_blue_pixels(page)

            report = f"📊 *نتائج فحص المربع {TARGET_SECTION}*\n\n"
            report += f"🎟️ *المربع:* `{TARGET_SECTION}` (CAT 5)\n"
            
            if is_seats_available:
                report += f"🟢 *الحالة:* تم التقاط درجة اللون المتاحة `rgb(59, 63, 98)` في الخريطة! 🎉\n"
            else:
                report += f"🔴 *الحالة:* لم يتم التقاط تذاكر بهذه الدرجة حالياً.\n"

            report += f"💵 *السعر:* `30 ﷼`"

            await page.screenshot(path="completed_screenshot.png")
            send_telegram_photo("completed_screenshot.png", report)

        except Exception as e:
            print(f"❌ حدث خطأ: {e}")
            await page.screenshot(path="error_screenshot.png")
            send_telegram_photo("error_screenshot.png", f"❌ توقف عند الخطأ:\n`{e}`")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_monitor())
