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
    cal_str += "```"

    cal_str += "\n**📌 當月請假名單對照：**\n"
    if not leave_days:
        cal_str += "• 本月目前沒有成員請假。\n"
    else:
        for d in sorted(leave_days.keys()):
            names_str = ", ".join(leave_days[d])
            cal_str += f"• **{month}/{d}**：{names_str}\n"

    return cal_str


class PersistentLeaveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 點擊填寫請假單", style=discord.ButtonStyle.green, custom_id="persistent_leave_btn_main_v3")
    async def open_leave_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = LeaveModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📅 重新整理方格月曆", style=discord.ButtonStyle.blurple, custom_id="persistent_leave_calendar_btn_v3")
    async def show_calendar(self, interaction: discord.Interaction, button: discord.ui.Button):
        calendar_view_text = generate_calendar_text(interaction.guild)
        await interaction.response.send_message(calendar_view_text, ephemeral=True)


class GameCharacterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        update_user_activity(message.author.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        if after.channel:
            update_user_activity(member.id)

    @app_commands.command(name="更新角色", description="登記或更新你在遊戲中的角色與職業")
    async def update_char(self, interaction: discord.Interaction, 角色名稱: str, 職業: str, 遊戲名稱: str = "靈谷"):
        update_user_activity(interaction.user.id)
        discord_id = interaction.user.id

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,))
        cursor.execute("SELECT id FROM game_characters WHERE discord_id = ? AND game_name = ?", (discord_id, 遊戲名稱))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("UPDATE game_characters SET character_name = ?, main_class = ? WHERE discord_id = ? AND game_name = ?", (角色名稱, 職業, discord_id, 遊戲名稱))
            action_type = "更新"
        else:
            cursor.execute("INSERT INTO game_characters (discord_id, game_name, character_name, main_class) VALUES (?, ?, ?, ?)", (discord_id, 遊戲名稱, 角色名稱, 職業))
            action_type = "新增"

        conn.commit()
        conn.close()
        await interaction.response.send_message(f"✅ **資料{action_type}成功！**\n• 遊戲：`{遊戲名稱}`\n• 角色 ID：`{角色名稱}`\n• 職業：`{職業}`", ephemeral=True)

    @app_commands.command(name="查角色", description="查詢指定成員或自己的遊戲角色資料")
    async def query_char(self, interaction: discord.Interaction, 成員: discord.Member = None):
        target = 成員 or interaction.user
        discord_id = target.id

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT game_name, character_name, main_class FROM game_characters WHERE discord_id = ?", (discord_id,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message(f"❌ `{target.display_name}` 目前尚未登記任何遊戲角色資料。", ephemeral=True)
            return

        desc = f"📋 **{target.display_name} 的角色清單**\n"
        for row in rows:
            desc += f"• **{row['game_name']}** | ID: `{row['character_name']}` | 職業: `{row['main_class']}`\n"

        await interaction.response.send_message(desc, ephemeral=True)

    @app_commands.command(name="架設請假面板", description="【管理員】在當前頻道發送常駐的請假按鈕與方格月曆面板")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_leave_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏖️ 靈谷公會 - 請假與方格行事曆",
            description="歡迎來到請假專區！如果有事需要請假，請點擊下方的綠色按鈕填寫假單。\n\n"
                        "• **填寫假單**：點擊按鈕彈出視窗輸入日期與原因。\n"
                        "• **管理審核**：假單會自動送往專用審核頻道進行審核。\n"
                        "• **查看月曆**：點擊藍色按鈕即可生成當月的方格日曆！",
            color=discord.Color.green()
        )
        view = PersistentLeaveView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 請假常駐面板已成功架設！", ephemeral=True)

    @app_commands.command(name="久未活躍", description="【管理員】查看超過指定天數沒有在 DC 發言或進語音的成員")
    @app_commands.checks.has_permissions(administrator=True)
    async def check_inactive(self, interaction: discord.Interaction, 天數: int = 14):
        guild = interaction.guild
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT discord_id, last_active FROM users")
        user_records = {row['discord_id']: row['last_active'] for row in cursor.fetchall()}
        conn.close()

        now = datetime.now()
        inactive_list = []

        for m in guild.members:
            if m.bot:
                continue
            last_active_str = user_records.get(m.id)
            if last_active_str:
                try:
                    last_active_dt = datetime.strptime(last_active_str, "%Y-%m-%d %H:%M:%S")
                    days_diff = (now - last_active_dt).days
                    if days_diff >= 天數:
                        inactive_list.append((m, days_diff))
                except Exception:
                    pass
            else:
                inactive_list.append((m, "從未互動"))

        if not inactive_list:
            await interaction.response.send_message(f"🎉 太棒了！伺服器內沒有超過 {天數} 天未活躍的成員！", ephemeral=True)
            return

        desc = f"⚠️ **超過 {天數} 天未在 DC 活躍的成員清單 (共 {len(inactive_list)} 人)：**\n"
        for m, days in inactive_list[:25]:
            day_text = f"超過 {days} 天" if isinstance(days, int) else days
            desc += f"• {m.mention} (`{m.display_name}`) — 最後活躍：*{day_text}*\n"

        await interaction.response.send_message(desc, ephemeral=True)

    @app_commands.command(name="未登記成員", description="【管理員】查看伺服器內尚未登記遊戲角色的成員")
    @app_commands.checks.has_permissions(administrator=True)
    async def check_unregistered(self, interaction: discord.Interaction):
        guild = interaction.guild
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT discord_id FROM game_characters")
        registered_ids = {row['discord_id'] for row in cursor.fetchall()}
        conn.close()

        unregistered_members = [m for m in guild.members if not m.bot and m.id not in registered_ids]

        if not unregistered_members:
            await interaction.response.send_message("🎉 太神啦！所有伺服器成員都已經登記過遊戲角色了！", ephemeral=True)
            return

        desc = f"⚠️ **尚未登記遊戲角色的成員清單 (共 {len(unregistered_members)} 人)：**\n"
        for m in unregistered_members[:30]:
            desc += f"• {m.mention} (`{m.display_name}`)\n"

        await interaction.response.send_message(desc, ephemeral=True)

    @app_commands.command(name="匯出資料", description="【管理員】將所有會員、遊戲角色與請假紀錄完整匯出為 CSV 檔案")
    @app_commands.checks.has_permissions(administrator=True)
    async def export_data(self, interaction: discord.Interaction):
        conn = get_db_connection()
        cursor = conn.cursor()
        # 完美整合會員、遊戲角色、請假紀錄的 LEFT JOIN 查詢
        cursor.execute("""
            SELECT 
                u.discord_id, 
                COALESCE(g.game_name, '未登記') as game_name, 
                COALESCE(g.character_name, '未登記') as character_name, 
                COALESCE(g.main_class, '未登記') as main_class, 
                COALESCE(l.start_date, '') as leave_start,
                COALESCE(l.end_date, '') as leave_end,
                COALESCE(l.reason, '') as leave_reason,
                COALESCE(l.status, '無') as leave_status,
                u.joined_at, 
                u.last_active 
            FROM users u 
            LEFT JOIN game_characters g ON u.discord_id = g.discord_id
            LEFT JOIN leaves l ON u.discord_id = l.discord_id
        """)
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        output.write("Discord_ID,Game_Name,Character_Name,Main_Class,Leave_Start,Leave_End,Leave_Reason,Leave_Status,Joined_At,Last_Active\n")
        
        for row in rows:
            cleaned_reason = str(row["leave_reason"]).replace(",", "，").replace("\n", " ")
            line = [
                str(row["discord_id"]),
                str(row["game_name"]),
                str(row["character_name"]),
                str(row["main_class"]),
                str(row["leave_start"]),
                str(row["leave_end"]),
                f'"{cleaned_reason}"',
                str(row["leave_status"]),
                str(row["joined_at"]),
                str(row["last_active"])
            ]
            output.write(",".join(line) + "\n")

        output.seek(0)
        file = discord.File(
            fp=io.BytesIO(output.getvalue().encode("utf-8-sig")),
            filename="guild_comprehensive_export.csv"
        )

        await interaction.response.send_message("📁 **公會全體資料（含遊戲角色與請假紀錄）匯出成功！**", file=file, ephemeral=True)


async def setup(bot):
    await bot.add_cog(GameCharacterCog(bot))
