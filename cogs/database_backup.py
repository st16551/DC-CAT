# ==================================================
# 檔案名稱：cogs/database_backup.py
# 檔案用途：雲端資料庫自動備份與開機還原系統（強效除錯版）
# ==================================================

import os
import discord
from discord.ext import commands, tasks

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057  # 你的 #備份 頻道 ID
        self.db_path = "guild_database.db"
        
        # 啟動時先執行還原，並開啟定時備份迴圈
        self.bot.loop.create_task(self.restore_database_from_discord())
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    # 1. 【還原機制】加強版：強制尋找並還原備份
    async def restore_database_from_discord(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.backup_channel_id)
        
        if not channel:
            print(f"[備份系統] ❌ 找不到指定的備份頻道 ID: {self.backup_channel_id}，請確認機器人是否有權限看到該頻道！")
            return

        print("[備份系統] 🔍 正在強力檢查 Discord 上的最新資料庫備份...")
        try:
            found_backup = False
            async for message in channel.history(limit=20):
                if message.attachments:
                    for attachment in message.attachments:
                        print(f"[備份系統] 發現附件: {attachment.filename}")
                        # 只要副檔名是 .db 或者是我們的資料庫名稱就直接抓下來
                        if attachment.filename.endswith(".db"):
                            await attachment.save(self.db_path)
                            print(f"[備份系統] ✅ 成功從 Discord 還原資料庫檔案: {attachment.filename}！")
                            found_backup = True
                            return
            
            if not found_backup:
                print("[備份系統] ⚠️ 備份頻道最近 20 則訊息內找不到任何 .db 檔案，將使用本地預設資料庫。")
        except Exception as e:
            print(f"[備份系統] ❌ 還原資料庫時發生嚴重錯誤: {e}")

    # 2. 【備份機制】每 3 小時自動備份一次
    @tasks.loop(hours=3)
    async def auto_backup_loop(self):
        await self.bot.wait_until_ready()
        if not os.path.exists(self.db_path):
            print("[備份系統] ⚠️ 本地找不到資料庫檔案，跳過此次備份。")
            return

        channel = self.bot.get_channel(self.backup_channel_id)
        if not channel:
            return

        print("[備份系統] 📦 正在將資料庫備份至 Discord...")
        try:
            file = discord.File(self.db_path, filename="guild_database.db")
            timestamp = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            await channel.send(content=f"📦 自動備份時間: `{timestamp}`", file=file)
            print("[備份系統] ✅ 資料庫備份至 Discord 成功！")
        except Exception as e:
            print(f"[備份系統] ❌ 備份上傳失敗: {e}")

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(DatabaseBackup(bot))
