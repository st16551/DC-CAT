async def startup_restore(self):
    await self.bot.wait_until_ready()
    channel = self.bot.get_channel(self.backup_channel_id)
    
    if channel:
        print("[備份系統] 🔍 【強制優先】正在從 Discord 搶先下載最新資料庫備份...")
        try:
            async for message in channel.history(limit=10):
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.filename.endswith(".db"):
                            temp_path = self.db_path + ".tmp"
                            await attachment.save(temp_path)
                            
                            if os.path.exists(self.db_path):
                                os.remove(self.db_path)
                            os.rename(temp_path, self.db_path)
                            
                            print(f"[備份系統] ✅ 【還原成功】已成功從 Discord 繼承舊資料庫檔案！")
                            break
                    else:
                        continue
                    break
        except Exception as e:
            print(f"[備份系統] ❌ 還原時發生錯誤: {e}")

    # 💡 關鍵：無論有沒有從 Discord 抓到備份，都必須在「下載結束後」才執行資料庫初始化與欄位檢查！
    from utils.database import init_db
    init_db()
    print("[備份系統] 🛠️ 資料庫結構已檢查並與舊資料完整對齊！")
