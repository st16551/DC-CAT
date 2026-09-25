import io
import sqlite3
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
import re

# 引入共用的絕對路徑資料庫連線
from utils.database import get_db_connection, DB_FILE

def update_user_activity(discord_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,))
    cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE discord_id = ?", (discord_id,))
    conn.commit()
    conn.close()


# ===================== 請假互動視窗與按鈕 =====================

class LeaveModal(discord.ui.Modal, title="📝 填寫公會請假單"):
    start_date_input = discord.ui.TextInput(
        label="開始日期 (格式: 月/日)",
        placeholder="例如：9/10",
        required=True,
        max_length=20
    )
    end_date_input = discord.ui.TextInput(
        label="結束日期 (格式: 月/日)",
        placeholder="例如：9/15 (如果當天請完可填同一天)",
        required=True,
        max_length=20
    )
    reason_input = discord.ui.TextInput(
        label="請假原因",
        placeholder="例如：家裡有事、期末考、加班等...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_date = self.start_date_input.value.strip()
            end_date = self.end_date_input.value.strip()

            # 日期格式驗證邏輯
            date_pattern = re.compile(r"^([1-9]|1[0-2])/([1-9]|[1-2][0-9]|3[0-1])$")
            
            if not date_pattern.match(start_date) or not date_pattern.match(end_date):
                await interaction.response.send_message(
                    "❌ **日期格式錯誤！** 請確實填寫類似 `9/10` 或 `09/15` 的有效日期格式，請勿填寫無效數字。",
                    ephemeral=True
                )
                return

            discord_id = interaction.user.id
            reason = self.reason_input.value

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,))
            cursor.execute(
                "INSERT INTO leaves (discord_id, reason, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)",
                (discord_id, reason, start_date, end_date, "審核中")
            )
            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="📄 【新請假申請待審核】",
                color=discord.Color.orange()
            )
            embed.add_field(name="請假成員", value=interaction.user.mention, inline=False)
            embed.add_field(name="請假區間", value=f"`{start_date}` ~ `{end_date}`", inline=False)
            embed.add_field(name="請假原因", value=reason, inline=False)
            embed.set_footer(text=f"申請人 ID: {discord_id}")

            view = LeaveReviewView()

            await interaction.response.send_message(
                content=f"✅ **{interaction.user.mention} 你的請假單已送出，已轉交管理員審核！**", 
                ephemeral=True
            )

            guild = interaction.guild
            review_channel = discord.utils.get(guild.text_channels, name="🔒│請假審核專區")

            if not review_channel:
                review_channel = discord.utils.find(lambda c: "請假審核" in c.name, guild.text_channels)
                
            if not review_channel:
                target_channel_name = "🔒│請假審核專區"
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True)
                }
                for role in guild.roles:
                    if role.permissions.administrator:
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

                try:
                    review_channel = await guild.create_text_channel(target_channel_name, overwrites=overwrites)
                except Exception as e_create:
                    print(f"⚠️ [請假系統] 自動建立審核頻道失敗: {e_create}")
                    review_channel = interaction.channel

            if review_channel:
                try:
                    await review_channel.send(embed=embed, view=view)
                except Exception as e_send:
                    print(f"⚠️ [請假系統] 傳送至審核頻道失敗: {e_send}")
                    await interaction.channel.send(embed=embed, view=view)
            else:
                await interaction.channel.send(embed=embed, view=view)

        except Exception as e:
            import traceback
            print("================ 嚴重的請假 Modal 崩潰錯誤 ================")
            traceback.print_exc()
            print("=========================================================")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 系統發生預期外的錯誤，已記錄至後台。錯誤代碼: `{e}`", ephemeral=True)
            except Exception:
                pass


class LeaveReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ 批准請假", style=discord.ButtonStyle.success, custom_id="leave_approve_btn_v5")
    async def approve_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理員可以審核請假！", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "✅ 【請假已批准】"
        embed.add_field(name="審核者", value=interaction.user.mention, inline=False)

        target_discord_id = int(embed.footer.text.split("ID: ")[-1])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE leaves SET status = '已批准' WHERE discord_id = ?", (target_discord_id,))
        conn.commit()
        conn.close()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ 已經批准了該位成員的請假申請。", ephemeral=True)

    @discord.ui.button(label="❌ 駁回申請", style=discord.ButtonStyle.danger, custom_id="leave_reject_btn_v5")
    async def reject_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理員可以審核請假！", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "❌ 【請假已駁回】"
        embed.add_field(name="審核者", value=interaction.user.mention, inline=False)

        target_discord_id = int(embed.footer.text.split("ID: ")[-1])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE leaves SET status = '已駁回' WHERE discord_id = ?", (target_discord_id,))
        conn.commit()
        conn.close()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        guild = interaction.guild
        target_member = guild.get_member(target_discord_id)
        
        notify_text = f"❌ **{interaction.user.mention} 已經駁回了您的請假申請。**"
        if target_member:
            try:
                await target_member.send(notify_text)
            except Exception:
                pass
            await interaction.followup.send(f"❌ 已經駁回了該位成員的請假申請，並已嘗試私訊通知 {target_member.mention}。", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ 已經駁回了該位成員的請假申請。", ephemeral=True)


def generate_calendar_text(guild):
    now = datetime.now()
    year = now.year
    month = now.month
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id, start_date, end_date FROM leaves WHERE status = '審核中' OR status LIKE '%批准%'")
    rows = cursor.fetchall()
    conn.close()

    leave_days = {}
    for discord_id, start_str, end_str in rows:
        member = guild.get_member(discord_id)
        name = member.display_name if member else "某員"
        try:
            s_m, s_d = map(int, start_str.replace("月", "/").replace("日", "").split("/"))
            e_m, e_d = map(int, end_str.replace("月", "/").replace("日", "").split("/"))
            if s_m == month:
                for d in range(s_d, e_d + 1):
                    if d not in leave_days:
                        leave_days[d] = set()
                    leave_days[d].add(name)
        except Exception:
            pass

    cal_str = f"```text\n      {year} 年 {month} 月行事曆\n"
    cal_str += "日   一   二   三   四   五   六\n"
    cal_str += "---------------------------------\n"

    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()
    start_weekday = (start_weekday + 1) % 7

    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    total_days = (next_month - first_day).days

    current_week = ""
    for _ in range(start_weekday):
        current_week += "      "

    for day in range(1, total_days + 1):
        day_str = f"{day:2d}"
        if day in leave_days:
            current_week += f"{day_str}📌 "
        else:
            current_week += f"{day_str}   "

        if len(current_week) >= 35 or (start_weekday + day) % 7 == 0:
            cal_str += current_week + "\n"
            current_week = ""

    if current_week:
        cal_str += current_week + "\n"
    cal_str += "
