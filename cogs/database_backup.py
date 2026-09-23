import os
import discord
from discord.ext import commands, tasks
import aiohttp

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 請把這裡換成你剛剛建立的「私密備份頻道 ID」
        self.backup_channel_id = 1552166997746262057  
        self.db_path = "guild_database.db"
        
        # 啟動時先執行還原，並開啟定時備份迴圈
        self.bot.loop.create_task(self.restore_database_from_discord())
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    # 1. 【還原機制】機器人開機時（on_ready 觸發後），去備份頻道抓最新的 db 檔
    async def restore_database_from_discord(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.backup_channel_id)
        
        if not channel:
            print(f"[備份系統] 找不到指定的備份頻道 ID: {self.backup_channel_id}")
            return

        print("[備份系統] 正在檢查 Discord 上的最新資料庫備份...")
        try:
            # 抓取頻道中的最後幾則訊息
            async for message in channel.history(limit=10):
                if message.attachments:
                    attachment = message.attachments[0]
                    # 確認附件是我們的資料庫檔案
                    if attachment.filename == "guild_database.db":
                        await attachment.save(self.db_path)
                        print("[備份系統] 成功從 Discord 還原最新資料庫！")
                        return
            
            print("[備份系統] 備份頻道中找不到現有的資料庫檔案，將使用本地預設（或全新）資料庫。")
        except Exception as e:
            print(f"[備份系統] 還原資料庫時發生錯誤: {e}")

    # 2. 【備份機制】設定一個定時任務，例如每 3 小時（或你可以自己改時間）自動上傳一次到 Discord
    @tasks.loop(hours=3)
    async def auto_backup_loop(self):
        await self.bot.wait_until_ready()
        if not os.path.exists(self.db_path):
            print("[備份系統] 本地找不到資料庫檔案，跳過此次備份。")
            return

        channel = self.bot.get_channel(self.backup_channel_id)
        if not channel:
            return

        print("[備份系統] 正在將資料庫備份至 Discord...")
        try:
            file = discord.File(self.db_path, filename="guild_database.db")
            timestamp = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            await channel.send(content=f"📦 自動備份時間: `{timestamp}`", file=file)
            print("[備份系統] 資料庫備份至 Discord 成功！")
        except Exception as e:
            print(f"[備份系統] 備份上傳失敗: {e}")

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(DatabaseBackup(bot))
