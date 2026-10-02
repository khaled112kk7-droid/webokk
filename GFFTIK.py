import os
import sys
import time
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TARGET_URL = os.getenv("TARGET_URL", "https://agc2026.tmtickets.sa/Events")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": False}
    try:
        requests.post(url, json=payload, timeout=10)
        print("تم إرسال التنبيه للتليجرام بنجاح.")
    except Exception as e:
        print(f"خطأ في إرسال التنبيه: {e}")

def monitor():
    # عدد الفعاليات الحالية في الصفحة
    INITIAL_EVENT_COUNT = 2
    
    print(f"بدء مراقبة الصفحة: {TARGET_URL}")
    
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
                page.wait_for_timeout(2000)
                
                # جلب جميع أزرار الحجز مع روابطها
                buttons = page.locator("a:has-text('FIND TICKETS')")
                current_count = buttons.count()
                
                print(f"عدد الفعاليات المكتشفة: {current_count}")
                
                if current_count > INITIAL_EVENT_COUNT:
                    # جلب رابط أحدث فعالية تمت إضافتها (عادة تكون في آخر الصفحة)
                    new_event_button = buttons.nth(current_count - 1)
                    href = new_event_button.get_attribute("href")
                    
                    # تحويل الرابط النسبي إلى رابط كامل إذا لزم الأمر
                    event_link = urljoin(TARGET_URL, href) if href else TARGET_URL
                    
                    msg = f"🚨 تذاكر نهائي خليجي\n\nرابط الفعالية:\n{event_link}"
                    print(msg)
                    
                    send_telegram_message(msg)
                    browser.close()
                    sys.exit(100) # لإيقاف الحلقة التكرارية في GitHub Actions
                
            except SystemExit:
                raise
            except Exception as e:
                print(f"خطأ أثناء فحص الصفحة: {e}")
            
            if i < 10:
                time.sleep(10)

        browser.close()

if __name__ == "__main__":
    monitor()
