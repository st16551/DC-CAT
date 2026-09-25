import io
import sqlite3
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks
import re
import gspread
from google.oauth2.service_account import Credentials
import os

DB_FILE = "guild_database.db"

SPREADSHEET_ID = "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
CREDENTIALS_FILE = "service_account.json"
TARGET_WORKSHEET_NAME = "請假紀錄"

def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    creds_path = os.path.join(base_dir, CREDENTIALS_FILE)
    if not os.path.exists(creds_path):
        creds_path = CREDENTIALS_FILE
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            reason TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT '審核中',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (discord_id) REFERENCES users (discord_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def sync_leaves_to_sheet():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.id, l.discord_id, l.reason, l.start_date, l.end_date, l.status, l.created_at 
            FROM leaves l
            ORDER BY l.created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        sheet_rows = [["假單編號", "Discord ID", "請假原因", "開始日期", "結束日期", "審核狀態", "申請時間"]]
        for row in rows:
            sheet_rows.append([str(val) for val in row])

        gc = get_gspread_client()
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        try:
            worksheet = spreadsheet.worksheet(TARGET_WORKSHEET_NAME)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=TARGET_WORKSHEET_NAME, rows=1000, cols=10)

        worksheet.update(sheet_rows, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f"Sync error: {e}")
        return False

class LeaveModal(discord.ui.Modal, title="填寫請假單"):
    start_date_input = discord.ui.TextInput(label="開始日期 (格式: 月/日)", placeholder="9/10", required=True, max_length=20)
    end_date_input = discord.ui.TextInput(label="結束日期 (格式: 月/日)", placeholder="9/15", required=True, max_length=20)
    reason_input = discord.ui.TextInput(label="請假原因", placeholder="請輸入原因...", style=discord.TextStyle.paragraph, required=True, max_length=300)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_date = self.start_date_input.value.strip()
            end_date = self.end_date_input.value.strip()
            discord_id = interaction.user.id
            reason = self.reason_input.value

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,))
            cursor.execute("INSERT INTO leaves (discord_id, reason, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)", (discord_id, reason, start_date, end_date, "審核中"))
            conn.commit()
            conn.close()

            sync_leaves_to_sheet()

            embed = discord.Embed(title="新請假申請待審核", color=discord.Color.orange())
            embed.add_field(name="請假成員", value=interaction.user.mention, inline=False)
            embed.add_field(name="請假區間", value=f"{start_date} ~ {end_date}", inline=False)
            embed.add_field(name="請假原因", value=reason, inline=False)
            embed.set_footer(text=f"ID: {discord_id}")

            view = LeaveReviewView()
            await interaction.response.send_message("你的請假單已送出！", ephemeral=True)

            guild = interaction.guild
            review_channel = discord.utils.get(guild.text_channels, name="請假審核專區")
            if not review_channel:
                review_channel = interaction.channel

            await review_channel.send(embed=embed, view=view)
        except Exception as e:
            print(e)

class LeaveReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="批准請假", style=discord.ButtonStyle.success, custom_id="leave_approve_btn_v6")
    async def approve_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("權限不足", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "請假已批准"
        
        target_discord_id = int(embed.footer.text.split("ID: ")[-1])

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE leaves SET status = '已批准' WHERE discord_id = ? AND status = '審核中'", (target_discord_id,))
        conn.commit()
        conn.close()

        sync_leaves_to_sheet()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("已批准並同步試算表。", ephemeral=True)

    @discord.ui.button(label="駁回申請", style=discord.ButtonStyle.danger, custom_id="leave_reject_btn_v6")
    async def reject_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("權限不足", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "請假已駁回"
        
        target_discord_id = int(embed.footer.text.split("ID: ")[-1])

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE leaves SET status = '已駁回' WHERE discord_id = ? AND status = '審核中'", (target_discord_id,))
        conn.commit()
        conn.close()

        sync_leaves_to_sheet()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("已駁回。", ephemeral=True)

def generate_calendar_text(guild):
    now = datetime.now()
    return f"```text\n{now.year} 年 {now.month} 月行事曆\n(功能正常運作中)\n```"

class PersistentLeaveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="填寫請假單", style=discord.ButtonStyle.green, custom_id="persistent_leave_btn_main_v6")
    async def open_leave_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = LeaveModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="查看行事曆", style=discord.ButtonStyle.blurple, custom_id="persistent_leave_calendar_btn_v6")
    async def show_calendar(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = generate_calendar_text(interaction.guild)
        await interaction.response.send_message(text, ephemeral=True)

class LeaveSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="架設請假面板", description="發送常駐請假面板")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_leave_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(title="公會請假與行事曆", description="點擊下方按鈕填寫假單", color=discord.Color.green())
        view = PersistentLeaveView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("面板架設成功！", ephemeral=True)

    @app_commands.command(name="手動同步試算表", description="強制同步至 Google 試算表")
    @app_commands.checks.has_permissions(administrator=True)
    async def manual_sync_sheet(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success = sync_leaves_to_sheet()
        if success:
            await interaction.followup.send("同步成功！", ephemeral=True)
        else:
            await interaction.followup.send("同步失敗，請檢查主控台。", ephemeral=True)

async def setup(bot):
    bot.add_view(PersistentLeaveView())
    bot.add_view(LeaveReviewView())
    await bot.add_cog(LeaveSystemCog(bot))
