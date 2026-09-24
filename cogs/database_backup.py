# ==================================================
# 檔案名稱：cogs/database_backup.py
# 檔案用途：Discord 頻道雲端備份與還原系統
# ==================================================

import os
import discord
from discord.ext import commands, tasks

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057
        self.db_path = "guild_database.db"
        
        self.bot.loop.create_task(self.startup_restore())
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

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

    @tasks.loop(hours=3)
    async def auto_backup_loop(self):
        await self.bot.wait_until_ready()
        if not os.path.exists(self.db_path):
            return

        channel = self.bot.get_channel(self.backup_channel_id)
        if not channel:
            return

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
