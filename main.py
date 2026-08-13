except Exception as e:
            print("❌ حدث خطأ أثناء الفحص: " + str(e))
        finally:
            browser.close()

def run_monitor():
    seen_events = load_seen_events()
    
    print("--- ⏱️ الفحص الأول (Cycle 1) ---")
    perform_check(seen_events)
    
    print("⏳ الانتظار لمدة 120 ثانية لإجراء الفحص الثاني...")
    time.sleep(120)
    
    print("--- ⏱️ الفحص الثاني (Cycle 2) ---")
    seen_events = load_seen_events()
    perform_check(seen_events)

    trigger_next_run()

if name == "__main__":
    run_monitor()
