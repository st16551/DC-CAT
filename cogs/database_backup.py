# ==================================================
# 檔案名稱：cogs/database_backup.py
# 檔案用途：Discord 頻道雲端備份與還原系統（強制同步還原版）
# ==================================================

import os
import datetime
import requests
import discord
from discord.ext import commands, tasks
from discord import app_commands

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057
        self.db_path = "guild_database.db"
        
        # 🚀 【強制同步還原】在載入瞬間直接透過 HTTP API 抓取雲端最大有效備份，不囉嗦直接覆蓋本地
        self.sync_restore_database()
        
        # 啟動定時自動備份
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    def get_taiwan_time(self):
        tw_timezone = datetime.timezone(datetime.timedelta(hours=8))
        return datetime.datetime.now(tw_timezone)

    def sync_restore_database(self):
        print("[備份系統] 🔍 【強制同步還原】正在透過 Discord API 尋找雲端最大備份檔...")
        try:
            headers = {"Authorization": f"Bot {self.bot.token}"} if hasattr(self.bot, "token") else {}
            # 直接透過 Discord REST API 抓取頻道歷史訊息（不需要等待 bot ready）
            url = f"https://discord.com/api/v10/channels/{self.backup_channel_id}/messages?limit=50"
            
            # 如果 bot token 存在隱藏屬性，使用 discord 的 internal token
            token = self.bot.http.token
            headers = {"Authorization": f"Bot {token}"}
            
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                print(f"[備份系統] ❌ 無法取得頻道訊息，API 回傳代碼: {response.status_code}")
                return

            messages = response.json()
            best_url = None
            max_size = 0

            for msg in messages:
                if "attachments" in msg:
                    for att in msg["attachments"]:
                        if att["filename"].endswith(".db"):
                            if att["size"] > max_size:
                                max_size = att["size"]
                                best_url = att["url"]

            if best_url and max_size > 20480: # 確保大於 20KB 才是有效檔案
                print(f"[備份系統] 📥 找到雲端最佳備份檔！大小: {max_size} bytes，正在下載...")
                file_res = requests.get(best_url)
                if file_res.status_code == 200:
                    temp_path = self.db_path + ".tmp"
                    with open(temp_path, "wb") as f:
                        f.write(file_res.content)
                    
                    if os.path.exists(self.db_path):
                        os.remove(self.db_path)
                    os.rename(temp_path, self.db_path)
                    print(f"[備份系統] ✅ 【還原成功】雲端 36KB 舊資料已成功強制覆蓋本地！")
                else:
                    print(f"[備份系統] ❌ 下載備份檔案失敗，HTTP 狀態碼: {file_res.status_code}")
            else:
                print(f"[備份系統] ⚠️ 雲端找不到大於 20KB 的有效備份檔，將使用本地預設狀態。")

        except Exception as e:
            print(f"[備份系統] ❌ 同步還原過程發生例外錯誤: {e}")

        # 最後初始化資料庫結構
        from utils.database import init_db
        init_db()
        print("[備份系統] 🛠️ 資料庫結構初始化完成。")

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
            timestamp = self.get_taiwan_time().strftime("%Y-%m-%d %H:%M:%S")
            await channel.send(content=f"📦 自動備份時間 (台灣時間): `{timestamp}`", file=file)
            print("[備份系統] ✅ 資料庫備份至 Discord 成功！")
        except Exception as e:
            print(f"[備份系統] ❌ 備份上傳失敗: {e}")

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="儲存資料", description="【管理員專用】手動將目前的資料庫立刻備份上傳到雲端頻道")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def manual_save(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        if not os.path.exists(self.db_path):
            await interaction.followup.send("❌ 找不到資料庫檔案 (`guild_database.db`)！", ephemeral=True)
            return

        channel = self.bot.get_channel(self.backup_channel_id)
        if not channel:
            await interaction.followup.send("❌ 找不到設定的備份頻道，請檢查 ID 是否正確！", ephemeral=True)
            return

        try:
            file = discord.File(self.db_path, filename="guild_database.db")
            timestamp = self.get_taiwan_time().strftime("%Y-%m-%d %H:%M:%S")
            await channel.send(content=f"💾 **[手動備份]** 管理員 `{interaction.user.name}` 觸發存檔\n⏰ 時間 (台灣時間): `{timestamp}`", file=file)
            await interaction.followup.send("✅ **資料庫已成功手動備份至雲端頻道！**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 備份上傳失敗: `{e}`", ephemeral=True)

    @app_commands.command(name="重製資料", description="【管理員專用】將資料庫表格清空重置（請小心使用！）")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def manual_reset(self, interaction: discord.Interaction):
        class ResetConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="確認重置資料庫", style=discord.ButtonStyle.danger)
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                import sqlite3
                conn = sqlite3.connect("guild_database.db")
                cursor = conn.cursor()
                
                tables = ["users", "game_characters", "leaves", "feedbacks", "checkin_system", "member_levels"]
                for table in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                conn.commit()
                conn.close()

                from utils.database import init_db
                init_db()

                for child in self.children:
                    child.disabled = True
                await button_interaction.response.edit_message(content="⚠️ **資料庫已被強制重置為初始狀態！**", view=self)
                self.stop()

            @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                for child in self.children:
                    child.disabled = True
                await button_interaction.response.edit_message(content="🛡️ 已取消重置操作，資料安全。", view=self)
                self.stop()

        view = ResetConfirmView()
        await interaction.response.send_message(
            "🚨 **警告：你正在嘗試重置整個公會資料庫！**\n這將會清除所有人的等級、SU 幣、發言數與簽到紀錄。確定要繼續嗎？",
            view=view,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(DatabaseBackup(bot))
