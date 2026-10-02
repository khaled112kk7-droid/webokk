import os
import sys
import time
from playwright.sync_api import sync_playwright
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TARGET_URL = os.getenv("TARGET_URL")

DATA_FILE = "last_page_content.txt"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print("تم إرسال التنبيه للتليجرام بنجاح.")
    except Exception as e:
        print(f"خطأ في إرسال التنبيه: {e}")

def save_content_to_file(content):
    """حفظ البيانات في ملف نصي بعد كل تحديث"""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"تم حفظ بيانات الصفحة في {DATA_FILE}")
    except Exception as e:
        print(f"خطأ أثناء حفظ الملف: {e}")

def load_previous_content():
    """قراءة المحتوى السابق إن وجد"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"خطأ أثناء قراءة الملف السابق: {e}")
    return None

def monitor():
    previous_content = load_previous_content()
    
    print(f"بدء مراقبة الصفحة باستخدام Playwright: {TARGET_URL}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        for i in range(1, 11):
            print(f"المحاولة {i} من 10...")
            try:
                page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
                current_content = page.content()
                
                # حفظ البيانات فوراً في ملف محلي
                save_content_to_file(current_content)
                
                if previous_content is not None:
                    if current_content != previous_content:
                        msg = f"🚨 تم اكتشاف تغيير في الصفحة!\nالموقع: {TARGET_URL}\nفي المحاولة رقم: {i}"
                        print(msg)
                        
                        # إرسال تنبيه فوراً
                        send_telegram_message(msg)
                        
                        browser.close()
                        # الخروج بكود خاص (Exit Code 100) ليخبر GitHub Actions بالتوقف عن التكرار
                        sys.exit(100)
                    else:
                        print("لا يوجد تغيير.")
                
                previous_content = current_content
                
            except SystemExit:
                raise
            except Exception as e:
                print(f"خطأ أثناء فحص الصفحة: {e}")
            
            if i < 10:
                time.sleep(10)

        browser.close()

if __name__ == "__main__":
    monitor()
