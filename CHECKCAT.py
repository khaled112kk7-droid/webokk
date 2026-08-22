import os
import asyncio
import json
import requests
from playwright.async_api import async_playwright

# 1. جلب البيانات السرية من متغيرات البيئة (GitHub Secrets)[span_0](start_span)[span_0](end_span)
PHONE = os.getenv("WEBOOK_EMIL")[span_1](start_span)[span_1](end_span)
PASSWORD = os.getenv("WEBOOK_PASS")[span_2](start_span)[span_2](end_span)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")[span_3](start_span)[span_3](end_span)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")[span_4](start_span)[span_4](end_span)
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")  # مفتاح API الخاص بـ 2Captcha

# 2. إعدادات الفعالية والفئات المطلوب مراقبتها[span_5](start_span)[span_5](end_span)
EVENT_URL = "https://webook.com/ar/SA/RUH/sports-event/events/rsl-26-27-al-shabab-vs-al-hilal-227984/book[span_6](start_span)"[span_6](end_span)
TARGET_CATEGORIES = ["Premium", "Premium 2"][span_7](start_span)[span_7](end_span)

# متغير تخزين المقاعد المستخرجة من الـ API[span_8](start_span)[span_8](end_span)
seats_data_store = [][span_9](start_span)[span_9](end_span)

def send_telegram(message):[span_10](start_span)[span_10](end_span)
    """إرسال التنبيه فوراً إلى التليجرام""[span_11](start_span)"[span_11](end_span)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage[span_12](start_span)"[span_12](end_span)
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}[span_13](start_span)[span_13](end_span)
    try:
        requests.post(url, json=payload, timeout=10)[span_14](start_span)[span_14](end_span)
    except Exception as e:[span_15](start_span)[span_15](end_span)
        print(f"فشل إرسال التنبيه عبر التليجرام: {e}")[span_16](start_span)[span_16](end_span)

async def solve_turnstile_captcha(page, sitekey):
    """حل كابتشا Cloudflare Turnstile عبر خدمة 2Captcha"""
    if not CAPTCHA_API_KEY:
        print("⚠️ لم يتم ضبط CAPTCHA_API_KEY في GitHub Secrets.")
        return False

    print("🧩 جاري إرسال الكابتشا لخدمة الحل التلقائي...")
    req_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method=turnstile&sitekey={sitekey}&pageurl={page.url}&json=1"
    res = requests.get(req_url).json()

    if res.get("status") != 1:
        print(f"❌ فشل طلب حل الكابتشا: {res.get('request')}")
        return False

    request_id = res.get("request")
    fetch_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={request_id}&json=1"

    # الانتظار حتى اكتمال الحل
    for _ in range(30):
        await asyncio.sleep(5)
        sol_res = requests.get(fetch_url).json()
        if sol_res.get("status") == 1:
            token = sol_res.get("request")
            print("✅ تم استلام توكن الكابتشا بنجاح! جاري تحقينه في الصفحة...")
            
            # إدخال التوكن المرجعي وتنفيذ استدعاء الكابتشا
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

async def handle_response(response):[span_17](start_span)[span_17](end_span)
    """التقاط الـ API الخاص بخريطة المقاعد أثناء التحميل واستخراج بيانات المقاعد""[span_18](start_span)"[span_18](end_span)
    global seats_data_store[span_19](start_span)[span_19](end_span)
    if "seat" in response.url or "map" in response.url or "layout" in response.url:[span_20](start_span)[span_20](end_span)
        try:[span_21](start_span)[span_21](end_span)
            if response.status == 200 and "json" in response.headers.get("content-type", ""):[span_22](start_span)[span_22](end_span)
                data = await response.json()[span_23](start_span)[span_23](end_span)
                if isinstance(data, dict):[span_24](start_span)[span_24](end_span)
                    seats_data_store = data.get("seats", data.get("data", []))[span_25](start_span)[span_25](end_span)
                elif isinstance(data, list):[span_26](start_span)[span_26](end_span)
                    seats_data_store = data[span_27](start_span)[span_27](end_span)
        except Exception:[span_28](start_span)[span_28](end_span)
            pass[span_29](start_span)[span_29](end_span)

async def close_cookie_banner(page):[span_30](start_span)[span_30](end_span)
    """إغلاق نافذة موافقة الكوكيز تلقائياً إذا ظهرت""[span_31](start_span)"[span_31](end_span)
    try:[span_32](start_span)[span_32](end_span)
        cookie_btn = page.locator("button:has-text('قبول الكل'), button:has-text('رفض الكل الغير ضروري')").first[span_33](start_span)[span_33](end_span)
        if await cookie_btn.is_visible(timeout=3000):[span_34](start_span)[span_34](end_span)
            await cookie_btn.click(force=True)[span_35](start_span)[span_35](end_span)
            print("تم إغلاق نافذة الكوكيز بنجاح.")[span_36](start_span)[span_36](end_span)
            await page.wait_for_timeout(1000)[span_37](start_span)[span_37](end_span)
    except Exception:[span_38](start_span)[span_38](end_span)
        pass[span_39](start_span)[span_39](end_span)

async def run_monitor():[span_40](start_span)[span_40](end_span)
    global seats_data_store[span_41](start_span)[span_41](end_span)
    async with async_playwright() as p:[span_42](start_span)[span_42](end_span)
        browser = await p.chromium.launch(headless=True)[span_43](start_span)[span_43](end_span)
        context = await browser.new_context()[span_44](start_span)[span_44](end_span)
        page = await context.new_page()[span_45](start_span)[span_45](end_span)

        page.on("response", handle_response)[span_46](start_span)[span_46](end_span)

        try:[span_47](start_span)[span_47](end_span)
            # --- الخطوة 1: الدخول المباشر لصفحة الفعالية ---[span_48](start_span)[span_48](end_span)
            print("الانتقال المباشر لصفحة الفعالية...")[span_49](start_span)[span_49](end_span)
            await page.goto(EVENT_URL, wait_until="networkidle")[span_50](start_span)[span_50](end_span)
            await close_cookie_banner(page)[span_51](start_span)[span_51](end_span)

            # --- الخطوة 2: تسجيل الدخول التلقائي ---[span_52](start_span)[span_52](end_span)
            email_input = page.locator("input[type='email'], input[placeholder*='you@email.com']").first[span_53](start_span)[span_53](end_span)
            if await email_input.is_visible(timeout=5000):[span_54](start_span)[span_54](end_span)
                print("جاري إدخال البريد الإلكتروني...")[span_55](start_span)[span_55](end_span)
                await email_input.fill(str(PHONE))[span_56](start_span)[span_56](end_span)
                await page.wait_for_timeout(1000)[span_57](start_span)[span_57](end_span)

                try:[span_58](start_span)[span_58](end_span)
                    await email_input.press("Enter")[span_59](start_span)[span_59](end_span)
                except Exception:[span_60](start_span)[span_60](end_span)
                    continue_btn = page.locator("button:has-text('تابع باستخدام البريد الإلكتروني')").first[span_61](start_span)[span_61](end_span)
                    await continue_btn.click(force=True)[span_62](start_span)[span_62](end_span)

                password_input = page.locator("input[type='password']").first[span_63](start_span)[span_63](end_span)
                await password_input.wait_for(timeout=15000)[span_64](start_span)[span_64](end_span)
                print("جاري إدخال كلمة المرور...")[span_65](start_span)[span_65](end_span)
                await password_input.fill(str(PASSWORD))[span_66](start_span)[span_66](end_span)
                await page.wait_for_timeout(1000)[span_67](start_span)[span_67](end_span)

                try:[span_68](start_span)[span_68](end_span)
                    await password_input.press("Enter")[span_69](start_span)[span_69](end_span)
                except Exception:[span_70](start_span)[span_70](end_span)
                    login_btn = page.locator("button:has-text('تسجيل الدخول')").first[span_71](start_span)[span_71](end_span)
                    await login_btn.click(force=True)[span_72](start_span)[span_72](end_span)

                await page.wait_for_timeout(3000)[span_73](start_span)[span_73](end_span)
                print("تم تسجيل الدخول بنجاح داخل التدفق!")[span_74](start_span)[span_74](end_span)

                # --- الخطوة 3: اختيار الفريق والموافقة واختيار التذاكر ---[span_75](start_span)[span_75](end_span)
                await close_cookie_banner(page)[span_76](start_span)[span_76](end_span)

                print("جاري النقر على (الهلال) بواسطة JavaScript المباشر...")[span_77](start_span)[span_77](end_span)
                await page.evaluate("""() => {[span_78](start_span)[span_78](end_span)
                    const pElements = Array.from(document.querySelectorAll('p'));[span_79](start_span)[span_79](end_span)
                    const hilalP = pElements.find(el => el.textContent.trim() === 'الهلال');[span_80](start_span)[span_80](end_span)
                    if (hilalP) {[span_81](start_span)[span_81](end_span)
                        const button = hilalP.closest('button');[span_82](start_span)[span_82](end_span)
                        if (button) button.click();[span_83](start_span)[span_83](end_span)
                        else hilalP.click();[span_84](start_span)[span_84](end_span)
                    }[span_85](start_span)[span_85](end_span)
                }""")[span_86](start_span)[span_86](end_span)

                print("✅ تم النقر على (الهلال) بنجاح.")[span_87](start_span)[span_87](end_span)
                await page.wait_for_timeout(1500)[span_88](start_span)[span_88](end_span)

                print("جاري النقر على مربع الموافقة...")[span_89](start_span)[span_89](end_span)
                await page.evaluate("""() => {[span_90](start_span)[span_90](end_span)
                    const labels = Array.from(document.querySelectorAll('label, span, div, p'));[span_91](start_span)[span_91](end_span)
                    const agreeEl = labels.find(el => el.textContent.includes('أوافق على حجز المقاعد المخصصة لجماهير فريقي المفضل فقط'));[span_92](start_span)[span_92](end_span)
                    if (agreeEl) agreeEl.click();[span_93](start_span)[span_93](end_span)
                }""")[span_94](start_span)[span_94](end_span)
                print("✅ تم النقر على مربع الموافقة بنجاح.")[span_95](start_span)[span_95](end_span)
                await page.wait_for_timeout(1500)[span_96](start_span)[span_96](end_span)

                print("جاري النقر على زر (التالي: اختيار التذاكر)...")[span_97](start_span)[span_97](end_span)
                await page.evaluate("""() => {[span_98](start_span)[span_98](end_span)
                    const buttons = Array.from(document.querySelectorAll('button'));[span_99](start_span)[span_99](end_span)
                    const nextBtn = buttons.find(btn => btn.textContent.includes('التالي: اختيار التذاكر') || btn.textContent.includes('اختيار التذاكر'));[span_100](start_span)[span_100](end_span)
                    if (nextBtn) nextBtn.click();[span_101](start_span)[span_101](end_span)
                }""")[span_102](start_span)[span_102](end_span)
                print("✅ تم الضغط على (التالي: اختيار التذاكر).")[span_103](start_span)[span_103](end_span)

            # --- فحص الكابتشا فوراً بعد الضغط على التالي ---
            await page.wait_for_timeout(3000)
            
            captcha_iframe = page.locator("iframe[src*='turnstile'], iframe[src*='recaptcha'], [data-sitekey]").first
            if await captcha_iframe.is_visible(timeout=5000):
                print("⚠️ تم ظهور الكابتشا بعد اختيار التذاكر! جاري فحص الـ Sitekey للحل...")
                sitekey = await page.evaluate("""() => {
                    const el = document.querySelector('[data-sitekey]');
                    return el ? el.getAttribute('data-sitekey') : null;
                }""")
                if sitekey:
                    solved = await solve_turnstile_captcha(page, sitekey)
                    if solved:
                        print("إعادة إرسال النقر على زر التالي لتجاوز الكابتشا...")
                        await page.evaluate("""() => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const nextBtn = buttons.find(btn => btn.textContent.includes('التالي: اختيار التذاكر') || btn.textContent.includes('اختيار التذاكر'));
                            if (nextBtn) nextBtn.click();
                        }""")

            # الانتظار لاكتمال فتح الخريطة وجلب بيانات الـ API
            await page.wait_for_timeout(6000)

            # --- الخطوة 4: فحص المقاعد وتحديد الأعداد المتبقية ---[span_104](start_span)[span_104](end_span)
            report = "📊 *تقرير المقاعد المتاحة (الهلال ضد الشباب):*\n\n[span_105](start_span)"[span_105](end_span)
            send_alert = False[span_106](start_span)[span_106](end_span)

            if seats_data_store:[span_107](start_span)[span_107](end_span)
                for category in TARGET_CATEGORIES:[span_108](start_span)[span_108](end_span)
                    available_count = len([[span_109](start_span)[span_109](end_span)
                        s for s in seats_data_store[span_110](start_span)[span_110](end_span)
                        if s.get("status") == "AVAILABLE" and category.lower() in str(s.get("category", "")).lower()[span_111](start_span)[span_111](end_span)
                    ])[span_112](start_span)[span_112](end_span)
                    
                    report += f"🔹 *{category}:* متبقي `{available_count}` مقعد.\n[span_113](start_span)"[span_113](end_span)
                    if available_count > 0:[span_114](start_span)[span_114](end_span)
                        send_alert = True[span_115](start_span)[span_115](end_span)

            else:[span_116](start_span)[span_116](end_span)
                for category in TARGET_CATEGORIES:[span_117](start_span)[span_117](end_span)
                    cat_locator = page.locator(f"text='{category}'")[span_118](start_span)[span_118](end_span)
                    if await cat_locator.is_visible():[span_119](start_span)[span_119](end_span)
                        parent_card = cat_locator.locator("xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'item')][1]")[span_120](start_span)[span_120](end_span)
                        text = await parent_card.inner_text()[span_121](start_span)[span_121](end_span)
                        
                        if "نفدت" in text or "Sold Out" in text:[span_122](start_span)[span_122](end_span)
                            report += f"❌ *{category}:* نفدت بالكامل.\n[span_123](start_span)"[span_123](end_span)
                        else:[span_124](start_span)[span_124](end_span)
                            report += f"✅ *{category}:* متاحة الآن للحجز!\n[span_125](start_span)"[span_125](end_span)
                            send_alert = True[span_126](start_span)[span_126](end_span)
                    else:[span_127](start_span)[span_127](end_span)
                        report += f"⚠️ *{category}:* غير ظاهرة بالقائمة.\n[span_128](start_span)"[span_128](end_span)

            # --- الخطوة 5: إرسال التقرير عبر التليجرام ---[span_129](start_span)[span_129](end_span)
            if send_alert:[span_130](start_span)[span_130](end_span)
                send_telegram(report)[span_131](start_span)[span_131](end_span)
                print("تم إرسال التقرير للتليجرام بنجاح!")[span_132](start_span)[span_132](end_span)
            else:[span_133](start_span)[span_133](end_span)
                print("لا توجد مقاعد متاحة للفئات المحددة حالياً.")[span_134](start_span)[span_134](end_span)

        except Exception as e:[span_135](start_span)[span_135](end_span)
            print(f"حدث خطأ أثناء تنفيذ السكربت: {e}")[span_136](start_span)[span_136](end_span)
        finally:[span_137](start_span)[span_137](end_span)
            await browser.close()[span_138](start_span)[span_138](end_span)

if __name__ == "__main__":[span_139](start_span)[span_139](end_span)
    asyncio.run(run_monitor())[span_140](start_span)[span_140](end_span)
