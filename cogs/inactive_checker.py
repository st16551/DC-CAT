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
        description="【管理員】精準檢測超過指定天數無互動的成員（自動排除請假中成員），同步至試算表"
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

        conn = get_db_connection()
        cursor = conn.cursor()

        # 🌟 1. 撈取所有「已批准」的請假紀錄，用來做豁免比對
        cursor.execute("""
            SELECT discord_id, start_date, end_date 
            FROM leaves 
            WHERE status LIKE '%批准%'
        """)
        leave_records = cursor.fetchall()

        # 處理請假名單轉換（檢查今天是否剛好在請假區間內）
        on_leave_discord_ids = set()
        for row_leave in leave_records:
            # 支援字典或 tuple 形式的資料庫回傳
            discord_id = row_leave["discord_id"] if isinstance(row_leave, sqlite3.Row) else row_leave[0]
            start_str = row_leave["start_date"] if isinstance(row_leave, sqlite3.Row) else row_leave[1]
            end_str = row_leave["end_date"] if isinstance(row_leave, sqlite3.Row) else row_leave[2]
            try:
                s_m, s_d = map(int, start_str.replace("月", "/").replace("日", "").split("/"))
                e_m, e_d = map(int, end_str.replace("月", "/").replace("日", "").split("/"))
                
                start_dt = datetime(now.year, s_m, s_d)
                end_dt = datetime(now.year, e_m, e_d, 23, 59, 59)

                if start_dt <= now <= end_dt:
                    on_leave_discord_ids.add(discord_id)
            except Exception:
                pass

        inactive_list = []
        sheet_rows = [["Discord ID", "使用者名稱", "顯示名稱", "累計訊息", "累計語音(時)", "最後活躍時間", "判定原因"]]
        excused_count = 0

        for member in guild.members:
            if member.bot:
                continue

            # 🌟 2. 如果該成員目前在請假保護名單中，直接跳過不視為未活躍！
            if member.id in on_leave_discord_ids:
                excused_count += 1
                continue

            # 查詢使用者的活躍與最後活動時間
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
            f"=== 超過 {days} 天無互動之精準未活躍成員清單 (共 {len(inactive_list)} 人，已自動排除 {excused_count} 位請假中成員) ===\n"
            f"檢測時間：{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            + "\n".join(inactive_list)
        )
        file = discord.File(
            fp=io.BytesIO(file_content.encode("utf-8")),
            filename=f"precise_inactive_{days}days.txt",
        )

        await interaction.followup.send(
            f"🎯 精準檢測完畢！符合未活躍條件的成員共 **{len(inactive_list)}** 人 *(另已自動豁免 {excused_count} 位請假中成員)*。{sync_status_msg}",
            file=file,
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(InactiveCheckerCog(bot))
