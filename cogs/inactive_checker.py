from datetime import datetime, timedelta
import io
import discord
from discord import app_commands
from discord.ext import commands
import gspread
from google.oauth2.service_account import Credentials
import os

from utils.database import get_db_connection

# 🔗 Google 試算表設定
SPREADSHEET_ID = "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
CREDENTIALS_FILE = "service_account.json"
TARGET_WORKSHEET_NAME = "未活躍清單"

def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    creds_path = os.path.join(base_dir, CREDENTIALS_FILE)
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)

class InactiveCheckerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="檢查未活躍",
        description="【管理員】精準檢測超過指定天數無互動的成員，同步至試算表"
    )
    @app_commands.describe(
        days="超過多少天未互動才視為未活躍（預設 14 天）",
        sync_sheet="是否同步寫入 Google 試算表指定分頁 (True/False)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_inactive_members(
        self, interaction: discord.Interaction, days: int = 14, sync_sheet: bool = False
    ):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        now = datetime.now()
        threshold_date = now - timedelta(days=days)

        inactive_list = []
        sheet_rows = [["Discord ID", "使用者名稱", "顯示名稱", "累計訊息", "累計語音(時)", "最後活躍時間", "判定原因"]]

        conn = get_db_connection()
        cursor = conn.cursor()

        for member in guild.members:
            if member.bot:
                continue

            # 查詢使用者的活躍與最後活動時間（對應你的 users 與 member_levels 表）
            cursor.execute("""
                SELECT u.last_active, m.messages_count, m.voice_hours 
                FROM users u 
                LEFT JOIN member_levels m ON u.discord_id = m.discord_id 
                WHERE u.discord_id = ?
            """, (member.id,))
            row = cursor.fetchone()

            is_inactive = False
            last_active_str = "從未記錄"
            last_active_time = None
            text_count = 0
            voice_hours = 0.0
            reason = ""

            if row:
                last_active_str = row["last_active"] or "從未記錄"
                text_count = row["messages_count"] if row["messages_count"] is not None else 0
                voice_hours = row["voice_hours"] if row["voice_hours"] is not None else 0.0
                
                if row["last_active"]:
                    try:
                        last_active_time = datetime.fromisoformat(row["last_active"])
                    except Exception:
                        pass

            # 精準判定邏輯：
            # 1. 如果資料庫根本沒有記錄，且加入時間超過指定天數 -> 判定未活躍
            # 2. 如果有記錄，但最後活躍時間小於門檻日期 -> 判定未活躍
            if not last_active_time:
                if member.joined_at and member.joined_at.replace(tzinfo=None) < threshold_date:
                    is_inactive = True
                    reason = "長期無互動且無任何活動紀錄"
            else:
                if last_active_time < threshold_date:
                    is_inactive = True
                    reason = f"超過 {days} 天未發言或參與語音"

            if is_inactive:
                inactive_list.append(
                    f"• @{member.name} ({member.display_name}) - 最後活躍：{last_active_str} | 訊息：{text_count} 條"
                )
                sheet_rows.append([
                    str(member.id),
                    str(member.name),
                    str(member.display_name),
                    str(text_count),
                    str(round(voice_hours, 2)),
                    last_active_str,
                    reason
                ])

        conn.close()

        # 📊 同步到 Google 試算表第二頁
        sync_status_msg = ""
        if sync_sheet:
            try:
                gc = get_gspread_client()
                spreadsheet = gc.open_by_key(SPREADSHEET_ID)
                
                try:
                    worksheet = spreadsheet.worksheet(TARGET_WORKSHEET_NAME)
                    worksheet.clear()
                except gspread.exceptions.WorksheetNotFound:
                    worksheet = spreadsheet.add_worksheet(title=TARGET_WORKSHEET_NAME, rows=1000, cols=10)

                worksheet.update(sheet_rows)
                sync_status_msg = f"\n📊 **已成功將精準未活躍名單同步至試算表分頁：「{TARGET_WORKSHEET_NAME}」！**"
            except Exception as e:
                sync_status_msg = f"\n⚠️ 試算表同步失敗：`{e}`"

        # 📁 產生成員名單 TXT 檔案
        file_content = (
            f"=== 超過 {days} 天無互動之精準未活躍成員清單 (共 {len(inactive_list)} 人) ===\n"
            f"檢測時間：{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            + "\n".join(inactive_list)
        )
        file = discord.File(
            fp=io.BytesIO(file_content.encode("utf-8")),
            filename=f"precise_inactive_{days}days.txt",
        )

        await interaction.followup.send(
            f"🎯 精準檢測完畢！符合未活躍條件的成員共 **{len(inactive_list)}** 人。{sync_status_msg}",
            file=file,
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(InactiveCheckerCog(bot))
