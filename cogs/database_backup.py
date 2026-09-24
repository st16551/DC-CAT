# ==================================================
# 檔案名稱：cogs/database_backup.py
# 檔案用途：Discord 頻道雲端備份與還原系統（重啟時不自動傳送新備份檔案）
# ==================================================

import os
import datetime
import urllib.request
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057
        self.db_path = "guild_database.db"
        
        # 🚀 啟動時不執行任何雲端存檔或覆蓋動作，保持本地乾淨
        # 如果需要定時備份，可以保留 loop，但它只會在時間到時計時執行，不會在「重開機」時立刻洗版
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    def get_taiwan_time(self):
        tw_timezone = datetime.timezone(datetime.timedelta(hours=8))
        return datetime.datetime.now(tw_timezone)

    def sync_restore_database(self):
        """手動讀取時會用到的還原核心邏輯"""
        print("[備份系統] 🔍 【手動還原】正在尋找雲端備份檔...")
        try:
            token = self.bot.http.token
            url = f"https://discord.com/api/v10/channels/{self.backup_channel_id}/messages?limit=50"
            
            req = urllib.request.Request(
                url, 
                headers={"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (Python)"}
            )
            
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    print(f"[備份系統] ❌ 無法取得頻道訊息，狀態碼: {response.status}")
                    return
                messages = json.loads(response.read().decode())

            target_url = None
            max_size = 0

            for msg in messages:
                if "attachments" in msg:
                    for att in msg["attachments"]:
                        if att["filename"].endswith(".db"):
                            if att["size"] > max_size:
                                max_size = att["size"]
                                target_url = att["url"]

            if target_url and max_size > 20480:
                print(f"[備份系統] 📥 正在下載雲端備份檔（大小: {max_size} bytes）...")
                file_req = urllib.request.Request(target_url, headers={"User-Agent": "DiscordBot (Python)"})
                with urllib.request.urlopen(file_req) as file_res:
                    if file_res.status == 200:
                        temp_path = self.db_path + ".tmp"
                        with open(temp_path, "wb") as f:
                            f.write(file_res.read())
                        
                        if os.path.exists(self.db_path):
                            os.remove(self.db_path)
                        os.rename(temp_path, self.db_path)
                        print(f"[備份系統] ✅ 【還原成功】已成功套用雲端備份！")
                    else:
                        print(f"[備份系統] ❌ 下載備份檔案失敗")
            else:
                print(f"[備份系統] ⚠️ 雲端找不到有效備份。")

        except Exception as e:
            print(f"[備份系統] ❌ 還原過程發生例外錯誤: {e}")

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
        # 💡 讓計時器等待機器人完全啟動後才開始計時，避免在啟動瞬間觸發上傳
        await asyncio.sleep(10) # 預留 10 秒緩衝，確保重啟不會立刻送出備份

    # ==================================================
    # 管理員專用：手動儲存資料指令
    # ==================================================
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

    # ==================================================
    # 管理員專用：手動讀取資料指令
    # ==================================================
    @app_commands.command(name="讀取資料", description="【管理員專用】從雲端頻道手動下載並還原最新的資料庫備份")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def manual_load(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            self.sync_restore_database()
            await interaction.followup.send("✅ **已成功從雲端頻道讀取並還原最新的資料庫！**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 讀取雲端備份失敗: `{e}`", ephemeral=True)

    # ==================================================
    # 管理員專用：重製資料指令（帶按鈕防呆）
    # ==================================================
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
