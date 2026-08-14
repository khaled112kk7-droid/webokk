import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GH_TOKEN = os.getenv("GH_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")

CACHE_FILE = "seen_events.json"
TARGET_URL = "https://webook.com/ar/explore?tag=football"

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ خطأ: لم يتم العثور على توكن التليجرام")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("📲 حالة إرسال تليجرام:", res.status_code)
    except Exception as e:
        print("❌ فشل إرسال التليجرام:", e)

def trigger_next_run():
    if not GH_TOKEN or not GITHUB_REPOSITORY:
        print("⚠️ لم يتم ضبط GH_TOKEN لتشغيل الدورة التالية تلقائياً.")
        return
    
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/workflows/monitor.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    data = {"ref": "main"}
    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        if res.status_code == 204:
            print("🔄 تم إرسال أمر التشغيل الفوري للدورة القادمة بنجاح!")
        else:
            print(f"⚠️ تعذر الإرسال: {res.status_code} - {res.text}")
    except Exception as e:
        print("❌ خطأ أثناء إرسال أمر التشغيل:", e)

def load_seen_events():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_events(seen_events):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_events), f, ensure_ascii=False, indent=2)

def perform_check(seen_events):
    new_found = 0
    print(f"🔍 بدء فحص الصفحة: {TARGET_URL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000)
            
            links = page.query_selector_all("a")
            print("📊 إجمالي الروابط بالصفحة:", len(links))
            
            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue
                
                if any(path in href for path in ['/e/', '/events/', '/matches/', '/sports/']):
                    full_url = href if href.startswith("http") else f"https://webook.com{href}"
                    event_id = full_url.split("?")[0]
                    
                    if event_id not in seen_events:
                        seen_events.add(event_id)
                        new_found += 1
                        
                        title = link.inner_text().strip().replace("\n", " ")
                        display_name = title if title else "مباراة / فعالية جديدة"
                        
                        msg = f"⚽ <b>فعالية جديدة على Webook!</b>\n\n📌 <b>العنوان:</b> {display_name}\n🔗 <b>الرابط:</b> {full_url}"
                        print("✨ تم كشف فعالية جديدة:", display_name)
                        send_telegram_message(msg)
            
            save_seen_events(seen_events)
            print("✅ اكتمل الفحص. فعاليات جديدة:", new_found)

        except Exception as e:
            print("❌ حدث خطأ أثناء الفحص:", e)
        finally:
            browser.close()

def run_monitor():
    # إجراء 10 فحوصات يفصل بين كل فحص وآخر 30 ثانية
    for cycle in range(1, 11):
        print(f"--- ⏱️ الفحص رقم ({cycle} من 10) ---")
        seen_events = load_seen_events()
        perform_check(seen_events)
        
        if cycle < 10:
            print("⏳ انتظار 30 ثانية للشفافية والسلاسة...")
            time.sleep(30)

    # طلب تشغيل الدورة القادمة فوراً
    trigger_next_run()

if __name__ == "__main__":
    run_monitor()
