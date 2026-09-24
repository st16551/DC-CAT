# ==================================================
# 檔案名稱：cogs/database_backup.py
# 檔案用途：Discord 頻道雲端備份與還原系統（含管理員指令與台灣時間）
# ==================================================

import os
import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands

class DatabaseBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_channel_id = 1552166997746262057
        self.db_path = "guild_database.db"
        
        self.bot.loop.create_task(self.startup_restore())
        self.auto_backup_loop.start()

    def cog_unload(self):
        self.auto_backup_loop.cancel()

    # 取得台灣時間 (UTC+8) 的 helper 函式
    def get_taiwan_time(self):
        tw_timezone = datetime.timezone(datetime.timedelta(hours=8))
        return datetime.datetime.now(tw_timezone)

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
            # 轉換為台灣時間格式
            timestamp = self.get_taiwan_time().strftime("%Y-%m-%d %H:%M:%S")
            await channel.send(content=f"📦 自動備份時間 (台灣時間): `{timestamp}`", file=file)
            print("[備份系統] ✅ 資料庫備份至 Discord 成功！")
        except Exception as e:
            print(f"[備份系統] ❌ 備份上傳失敗: {e}")

    @auto_backup_loop.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

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
