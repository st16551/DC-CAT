import os
import discord
from discord.ext import commands, tasks

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057
        self.db_path = "guild_database.db"
        
        self.bot.loop.create_task(self.restore_database_urgently())
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

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
                            temp_path = self.db_path + ".tmp"
                            await attachment.save(temp_path)
                            
                            if os.path.exists(self.db_path):
                                os.remove(self.db_path)
                            os.rename(temp_path, self.db_path)
                            
                            print(f"[備份系統] ✅ 成功搶先還原資料庫檔案: {attachment.filename}！")
                            return
            
            print("[備份系統] ⚠️ 備份頻道中找不到任何 .db 檔案。")
        except Exception as e:
            print(f"[備份系統] ❌ 還原資料庫時發生嚴重錯誤: {e}")

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
