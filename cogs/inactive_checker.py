from datetime import datetime, timedelta
import io
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# 引入共用的資料庫連線或資料變數
from utils.database import get_db_connection
from utils.sheets import parse_leave_range, sync_all_members_to_sheet


class InactiveCheckerCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="檢查未活躍",
        description="【管理員】精準檢測超過指定天數無互動的成員（自動排除請假中成員）並導出清單 (TXT)",
    )
    @app_commands.describe(days="超過多少天未互動才視為未活躍（預設 14 天）")
    @app_commands.checks.has_permissions(administrator=True)
    async def check_inactive_members(
        self, interaction: discord.Interaction, days: int = 14
    ):
        # 預先回覆訊息，避免處理時間過長導致互動逾時
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        now = datetime.now()
        threshold_date = now - timedelta(days=days)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 🌟 1. 撈取所有「已批准」的請假紀錄，用來做豁免比對
        cursor.execute(
            """
            SELECT discord_id, start_date, end_date 
            FROM leaves 
            WHERE status LIKE '%批准%'
        """
        )
        leave_records = cursor.fetchall()

        # 處理請假名單轉換（檢查今天是否剛好在請假區間內）
        on_leave_discord_ids = set()
        for row_leave in leave_records:
            # 支援字典或 tuple 形式的資料庫回傳
            discord_id = (
                row_leave["discord_id"]
                if isinstance(row_leave, sqlite3.Row)
                else row_leave[0]
            )
            start_str = (
                row_leave["start_date"]
                if isinstance(row_leave, sqlite3.Row)
                else row_leave[1]
            )
            end_str = (
                row_leave["end_date"]
                if isinstance(row_leave, sqlite3.Row)
                else row_leave[2]
            )
            start_dt, end_dt = parse_leave_range(start_str, end_str, now)
            if start_dt and end_dt and start_dt <= now <= end_dt:
                on_leave_discord_ids.add(discord_id)

        inactive_list = []
        excused_count = 0

        for member in guild.members:
            if member.bot:
                continue

            # 🌟 2. 如果該成員目前在請假保護名單中，直接跳過不視為未活躍！
            if member.id in on_leave_discord_ids:
                excused_count += 1
                continue

            # 查詢使用者的活躍與最後活動時間 (相容 u.last_active 與 member_levels 結構)
            cursor.execute(
                """
                SELECT u.last_active, m.messages_count, m.voice_hours 
                FROM users u 
                LEFT JOIN member_levels m ON u.discord_id = m.discord_id 
                WHERE u.discord_id = ?
            """,
                (member.id,),
            )
            row = cursor.fetchone()

            is_inactive = False
            last_active_str = "從未記錄"
            last_active_time = None
            text_count = 0
            reason = ""

            if row:
                last_active_str = row["last_active"] or "從未記錄"
                text_count = (
                    row["messages_count"]
                    if row["messages_count"] is not None
                    else 0
                )

                if row["last_active"]:
                    try:
                        last_active_time = datetime.fromisoformat(
                            row["last_active"]
                        )
                    except Exception:
                        try:
                            last_active_time = datetime.strptime(
                                row["last_active"], "%Y-%m-%d %H:%M:%S"
                            )
                        except Exception:
                            pass

            # 精準判定邏輯
            if not last_active_time:
                if (
                    member.joined_at
                    and member.joined_at.replace(tzinfo=None) < threshold_date
                ):
                    is_inactive = True
                    reason = "長期無互動且無任何活動紀錄"
            else:
                if last_active_time < threshold_date:
                    is_inactive = True
                    reason = f"超過 {days} 天未發言或參與語音"

            if is_inactive:
                inactive_list.append(
                    f"• 帳號：{member.name} | 暱稱：{member.display_name} (ID: {member.id}) — 最後活躍：{last_active_str} | 訊息：{text_count} 條 | 原因：{reason}"
                )

        conn.close()

        # 📁 產生成員名單 TXT 檔案
        if not inactive_list:
            await interaction.followup.send(
                f"🎉 太棒了！伺服器內沒有超過 {days} 天未活躍的成員 *(已自動豁免 {excused_count} 位請假中成員)*。",
                ephemeral=True,
            )
            return

        file_content = (
            f"=== {guild.name} 超過 {days} 天未在 DC 活躍的成員清單 (已自動豁免 {excused_count} 位請假中成員) ===\n"
            f"檢測時間：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"符合條件總人數：{len(inactive_list)} 人\n"
            f"======================================================================\n\n"
            + "\n".join(inactive_list)
        )

        file = discord.File(
            fp=io.BytesIO(file_content.encode("utf-8-sig")),
            filename=f"precise_inactive_{days}days.txt",
        )

        await interaction.followup.send(
            f"⚠️ **已成功產生成員清單！** 超過 {days} 天未在 DC 活躍的成員共 **{len(inactive_list)}** 人 *(已自動略過 {excused_count} 位請假中成員)*，檔案已附在下方：",
            file=file,
            ephemeral=True,
        )
        try:
            result = sync_all_members_to_sheet(guild, days=days)
            await interaction.followup.send(
                f"📑 已同步試算表：成員名單 `{result.get('members', 0)}` 人、好朋友 `{result.get('friends', 0)}` 人。",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"⚠️ 名單已產出，但試算表同步失敗：`{e}`",
                ephemeral=True,
            )

    @app_commands.command(
        name="同步試算表",
        description="【管理員】依身分組同步：成員+分會→成員名單，其餘有成員身分組→好朋友",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_sheet_status(self, interaction: discord.Interaction, days: int = 14):
        await interaction.response.defer(ephemeral=True)
        try:
            result = sync_all_members_to_sheet(interaction.guild, days=days)
            await interaction.followup.send(
                f"✅ 同步完成。\n"
                f"• 成員名單（有「成員」+分會身分組）：`{result.get('members', 0)}` 人\n"
                f"• 好朋友（有「成員」但沒有分會）：`{result.get('friends', 0)}` 人\n"
                f"• 已連動請假／活躍／未活躍分頁（僅正式成員）。",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ 同步失敗：`{e}`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(InactiveCheckerCog(bot))
