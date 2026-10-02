import os
import time
import requests

# إعدادات التليجرام والموقع من البيئة
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TARGET_URL = "https://agc2026.tmtickets.sa/Events"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"خطأ في إرسال التنبيه: {e}")

def monitor():
    previous_content = None
    
    print(f"بدء مراقبة الصفحة: {TARGET_URL}")
    
    for i in range(1, 11):
        print(f"المحاولة {i} من 10...")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(TARGET_URL, headers=headers, timeout=10)
            current_content = response.text
            
            if previous_content is not None:
                if current_content != previous_content:
                    msg = f"🚨 تم اكتشاف تغيير في الصفحة!\nالموقع: {TARGET_URL}\nفي المحاولة رقم: {i}"
                    print(msg)
                    send_telegram_message(msg)
                    return  # إيقاف التكرار عند اكتشاف التغيير
                else:
                    print("لا يوجد تغيير.")
            
            previous_content = current_content
            
        except Exception as e:
            print(f"خطأ أثناء جلب الصفحة: {e}")
        
        # الانتظار 10 ثوانٍ قبل التحديث القادم (عدا المحاولة الأخيرة)
        if i < 10:
            time.sleep(10)

if __name__ == "__main__":
    monitor()
