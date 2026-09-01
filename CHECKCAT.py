# --- 1. اختيار الشعار/الفريق ---
                print("⚽ [خطوة 5] جاري اختيار الفريق المطلوب...")
                
                # يمكنك تغيير اسم الفريق هنا إلى "الاتحاد" أو "النصر"
                TARGET_TEAM = "الاتحاد"

                # الخيار الأول والأضمن: استهداف زر الفريق الذي يحتوي على alt الصورة الخاصة به
                team_card = page.locator(f"button[data-testid^='ui_toggle_favorite_team']:has(img[alt='{TARGET_TEAM}'])").first
                
                # الخيار البديل إذا لم يجد الصورة: الاستهداف بداخل زر الفريق الذي يحوي النص
                if not await team_card.is_visible(timeout=3000):
                    team_card = page.locator(f"button[data-testid^='ui_toggle_favorite_team']:has-text('{TARGET_TEAM}')").first

                await team_card.wait_for(state="visible", timeout=7000)
                await team_card.click(force=True)
                print(f"✅ تم تحديد فريق ({TARGET_TEAM}) بنجاح.")
                
                await page.wait_for_timeout(1000)
