async def startup_restore(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.backup_channel_id)
        
        if channel:
            print("[備份系統] 🔍 【智慧還原】正在掃描雲端頻道中最大的有效備份檔...")
            try:
                best_attachment = None
                max_size = 0
                
                # 往回檢查最近 50 筆訊息，找出裡面檔案最大的 .db 檔
                async for message in channel.history(limit=50):
                    if message.attachments:
                        for attachment in message.attachments:
                            if attachment.filename.endswith(".db"):
                                # 找出檔案大小大於 20 KB 且為歷史中最大的檔案
                                if attachment.size > max_size:
                                    max_size = attachment.size
                                    best_attachment = attachment
                
                if best_attachment and max_size > 20480: # 確保大於 20KB 才是有效資料
                    temp_path = self.db_path + ".tmp"
                    await best_attachment.save(temp_path)
                    
                    if os.path.exists(self.db_path):
                        os.remove(self.db_path)
                    os.rename(temp_path, self.db_path)
                    
                    print(f"[備份系統] ✅ 【還原成功】已成功找回最完整的備份檔！(大小: {max_size} bytes)")
                else:
                    print("[備份系統] ⚠️ 找不到大於 20KB 的有效備份檔，將使用本地現有資料庫。")
                    
            except Exception as e:
                print(f"[備份系統] ❌ 還原時發生錯誤: {e}")

        # 確保在還原動作完成後，才進行資料庫結構初始化與檢查
        from utils.database import init_db
        init_db()
        print("[備份系統] 🛠️ 資料庫結構已檢查並與備份資料完整對齊！")
