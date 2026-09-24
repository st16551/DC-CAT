import os
import sqlite3
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
import gspread
from google.oauth2.service_account import Credentials

DB_FILE = "guild_database.db"

# 🔗 Google 試算表設定
SPREADSHEET_ID = "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
CREDENTIALS_FILE = "service_account.json"
TARGET_WORKSHEET_NAME = "活躍表"

# 暫存語音進入時間 (discord_id: datetime)
voice_sessions = {}

def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    creds_path = os.path.join(base_dir, CREDENTIALS_FILE)
    if not os.path.exists(creds_path):
        creds_path = CREDENTIALS_FILE
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)

def init_activity_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            voice_seconds INTEGER DEFAULT 0,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_activity_db()

# 📊 同步活躍數據到 Google 試算表
def sync_activity_to_sheet():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT discord_id, message_count, voice_seconds, last_active 
            FROM users 
            ORDER BY (message_count + ((voice_seconds / 60.0) * 3)) DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        # 整理試算表標題與內容
        sheet_rows = [["Discord ID", "發言則數", "語音總秒數", "語音總時數(小時)", "最後活躍時間"]]
        for row in rows:
            discord_id, message_count, voice_seconds, last_active = row
            voice_hours = round(voice_seconds / 3600, 2)
            sheet_rows.append([str(discord_id), message_count, voice_seconds, voice_hours, last_active])

        gc = get_gspread_client()
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        try:
            worksheet = spreadsheet.worksheet(TARGET_WORKSHEET_NAME)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=TARGET_WORKSHEET_NAME, rows=1000, cols=10)

        worksheet.update(sheet_rows)
        return True
    except Exception as e:
        print(f"⚠️ [活躍表試算表同步失敗]: {e}")
        return False


class ActivityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_sync_activity.start()

    def cog_unload(self):
        self.auto_sync_activity.cancel()

    # ⏱️ 每天自動同步一次活躍數據到試算表（可依需求調整頻率）
    @tasks.loop(hours=24)
    async def auto_sync_activity(self):
        sync_activity_to_sheet()

    @auto_sync_activity.before_loop
    async def before_auto_sync(self):
        await self.bot.wait_until_ready()

    # 💬 監聽文字訊息：自動累計發言數與最後活躍時間
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        discord_id = message.author.id
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,))
        cursor.execute("""
            UPDATE users 
            SET message_count = message_count + 1, last_active = ? 
            WHERE discord_id = ?
        """, (now_str, discord_id))
        conn.commit()
        conn.close()

    # 🎙️ 監聽語音狀態：精準計算進入與離開的語音總秒數
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        discord_id = member.id
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,))

        # 進入語音
        if before.channel is None and after.channel is not None:
            voice_sessions[discord_id] = now

        # 離開語音
        elif before.channel is not None and after.channel is None:
            if discord_id in voice_sessions:
                start_time = voice_sessions.pop(discord_id)
                duration = int((now - start_time).total_seconds())
                if duration > 0:
                    cursor.execute("""
                        UPDATE users 
                        SET voice_seconds = voice_seconds + ?, last_active = ? 
                        WHERE discord_id = ?
                    """, (duration, now_str, discord_id))
        conn.commit()
        conn.close()

    # 🏆 活躍排行榜指令（高語音權重公式）
    @app_commands.command(name="活躍排行", description="查看公會成員的文字與語音活躍排行榜")
    async def show_leaderboard(self, interaction: discord.Interaction):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # ⚖️ 調整權重：1 則訊息 = 1 分，每分鐘語音 = 3 分
        cursor.execute("""
            SELECT discord_id, message_count, voice_seconds, last_active 
            FROM users 
            ORDER BY (message_count + ((voice_seconds / 60.0) * 3)) DESC 
            LIMIT 10
        """)
        rows = cursor.fetchall()
        conn.close()

        embed = discord.Embed(title="🏆 公會成員活躍排行榜 (語音高權重)", color=discord.Color.gold())
        
        if not rows:
            embed.description = "目前尚無任何活躍紀錄。"
        else:
            desc = ""
            for idx, (uid, msg_count, voice_sec, last_act) in enumerate(rows, 1):
                member = interaction.guild.get_member(uid)
                name = member.display_name if member else f"未知用戶({uid})"
                voice_hours = round(voice_sec / 3600, 1)
                desc += f"**#{idx}** {name}\n 💬 發言: `{msg_count}` 則 | 🎙️ 語音: `{voice_hours}` 小時\n\n"
            embed.description = desc

        await interaction.response.send_message(embed=embed, ephemeral=False)

    # 📊 手動同步活躍表指令（管理員專用）
    @app_commands.command(name="同步活躍表", description="【管理員】立即將目前所有成員的活躍數據同步至 Google 試算表")
    @app_commands.checks.has_permissions(administrator=True)
    async def manual_sync_activity(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if sync_activity_to_sheet():
            await interaction.followup.send("📊 **活躍表同步成功！** 資料已更新至 Google 試算表的「活躍表」分頁。", ephemeral=True)
        else:
            await interaction.followup.send("❌ **同步失敗！** 請檢查終端機錯誤訊息與憑證設定。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ActivityCog(bot))
