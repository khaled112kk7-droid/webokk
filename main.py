import os
import json
import requests
from playwright.sync_api import sync_playwright

# قراءة البيانات الحساسة من إعدادات GitHub Secrets
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATA_FILE = "seen_events.json"

def send_telegram(message):
    """إرسال تنبيه إلى تليجرام"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"خطأ في إرسال رسالة تليجرام: {e}")

def load_seen_events():
    """تحميل قائمة الفعاليات المسجلة سابقاً"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen_events(events):
    """حفظ الفعاليات في ملف لعدم تكرار التنبيهات"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(list(events), f, ensure_ascii=False, indent=2)

def run():
    TARGET_URL = "https://webook.com/ar/events"
    seen_events = load_seen_events()
    current_events = set()
    new_found = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # استخراج روابط الفعاليات
            event_elements = page.query_selector_all("a[href*='/events/']")
            for el in event_elements:
                title = el.inner_text().strip()
                href = el.get_attribute("href")
                if title and href:
                    full_url = href if href.startswith("http") else f"https://webook.com{href}"
                    current_events.add(full_url)
                    
                    if full_url not in seen_events:
                        new_found.append((title, full_url))

            # إرسال تنبيه للفعاليات الجديدة فقط
            for title, url in new_found:
                msg = f"🚨 فعالية جديدة على Webook!**\n\n📌 **الاسم: {title}\n🔗 الرابط: {url}"
                send_telegram(msg)
                print(f"تم إرسال تنبيه بفعالية جديدة: {title}")

            # تحديث قائمة الفعاليات
            seen_events.update(current_events)
            save_seen_events(seen_events)

        except Exception as e:
            print(f"حدث خطأ أثناء التشغيل: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
