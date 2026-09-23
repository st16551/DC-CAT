# ==================================================
# 檔案名稱：cogs/database_backup.py
# 檔案用途：雲端資料庫自動備份與開機搶先還原系統
# ==================================================

import os
import discord
from discord.ext import commands, tasks

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057  # 你的 #備份 頻道 ID
        self.db_path = "guild_database.db"
        
        # 【關鍵修改】不要用背景 Task，改用直接註冊成事件，確保開機瞬間優先執行還原
        self.bot.loop.create_task(self.restore_database_urgently())
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    # 1. 【同步搶先還原機制】連線後第一時間強制抓取並覆蓋
    async def restore_database_urgently(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.backup_channel_id)
        
        if not channel:
            print(f"[備份系統] ❌ 找不到指定的備份頻道 ID: {self.backup_channel_id}")
            return

        print("[備份系統] 🔍 正在從 Discord 搶先下載最新資料庫備份...")
        try:
            async for message in channel.history(limit=10):
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.filename.endswith(".db"):
                            # 如果本地有舊的，先嘗試關閉連線或直接覆蓋
                            temp_path = self.db_path + ".tmp"
                            await attachment.save(temp_path)
                            
                            # 安全取代舊的資料庫檔案
                            if os.path.exists(self.db_path):
                                os.remove(self.db_path)
                            os.rename(temp_path, self.db_path)
                            
                            print(f"[備份系統] ✅ 成功搶先還原資料庫檔案: {attachment.filename}！")
                            print("[備份系統] 💡 建議重啟一次機器人以重新載入最新資料庫數據。")
                            return
            
            print("[備份系統] ⚠️ 備份頻道中找不到任何 .db 檔案。")
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
