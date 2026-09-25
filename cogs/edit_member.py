import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
import gspread
from google.oauth2.service_account import Credentials

DB_FILE = "guild_database.db"
SPREADSHEET_ID = "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
CREDENTIALS_FILE = "credentials.json"

# 📝 身分組 ID 對應字典
ROLE_IDS = {
    "牧師": 1529725865024557196,
    "聖騎": 1529726272471568454,
    "槍手": 1529726360568987708,
    "死靈": 1529726490734886922,
    "法師": 1529726652341420113,
    "忍者": 1529726861570216083,
    "編織": 1529727042516422798,
    "戰士": 1529734718193668127,
    
    # 分會身分組
    "1會": 1541087729088200765,
    "2会": 1541087803151098079,
    "3会": 1541087848298446998,
}

def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    return client

class EditMemberByDiscordModal(discord.ui.Modal, title="🛠️ 修改成員資料"):
    def __init__(self, target_discord_id: int, db_data):
        super().__init__()
        self.target_discord_id = target_discord_id
        self.db_data = db_data

        self.new_char_name_input = discord.ui.TextInput(
            label="新遊戲角色 ID",
            default=db_data[3] if db_data else "",
            max_length=50,
            required=True
        )
        self.class_input = discord.ui.TextInput(
            label="新職業 (聖騎/戰士/法師/死靈/牧師/槍手/忍者/編織)",
            default=db_data[4] if db_data else "聖騎",
            max_length=20,
            required=True
        )
        self.branch_input = discord.ui.TextInput(
            label="新分配分會 (1會 / 2會 / 3會)",
            default=db_data[5] if db_data else "1會",
            max_length=10,
            required=True
        )
        
        self.add_item(self.new_char_name_input)
        self.add_item(self.class_input)
        self.add_item(self.branch_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_char_name = self.new_char_name_input.value.strip()
        new_class = self.class_input.value.strip()
        new_branch = self.branch_input.value.strip()

        if new_branch not in ["1會", "2會", "3會"]:
            await interaction.response.send_message("❌ 分會名稱必須是 `1會`、`2會` 或 `3會`！", ephemeral=True)
            return

        old_char_name = self.db_data[3] if self.db_data else "未知"
        old_class = self.db_data[4] if self.db_data else ""
        old_branch = self.db_data[5] if self.db_data else ""

        # 1. 更新本地 SQLite
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE game_characters 
            SET character_name = ?, main_class = ?, branch = ?
            WHERE discord_id = ?
        """, (new_char_name, new_class, new_branch, self.target_discord_id))
        conn.commit()
        conn.close()

        # 2. 同步更新 Google 試算表[cite: 1]
        sheet_updated = False
        try:
            client = get_gspread_client()
            sheet = client.open_by_key(SPREADSHEET_ID).sheet1
            
            cell = sheet.find(str(self.target_discord_id))
            if cell:
                row_idx = cell.row
                sheet.update_cell(row_idx, 4, new_char_name)
                sheet.update_cell(row_idx, 5, new_class)
                sheet.update_cell(row_idx, 6, new_branch)
                sheet_updated = True
        except Exception as e:
            print(f"❌ 同步 Google 試算表失敗：{e}")

        # 3. 更新 Discord 身分組
        guild = interaction.guild
        member = guild.get_member(self.target_discord_id)
        role_changes_msg = []

        if member:
            if old_class != new_class:
                if old_class and old_class in ROLE_IDS:
                    old_r = guild.get_role(ROLE_IDS[old_class])
                    if old_r and old_r in member.roles:
                        await member.remove_roles(old_r)
                if new_class in ROLE_IDS:
                    new_r = guild.get_role(ROLE_IDS[new_class])
                    if new_r:
                        await member.add_roles(new_r)
                        role_changes_msg.append(f"職業: {new_class}")

            if old_branch != new_branch:
                if old_branch and old_branch in ROLE_IDS:
                    old_br = guild.get_role(ROLE_IDS[old_branch])
                    if old_br and old_br in member.roles:
                        await member.remove_roles(old_br)
                if new_branch in ROLE_IDS:
                    new_br = guild.get_role(ROLE_IDS[new_branch])
                    if new_br:
                        await member.add_roles(new_br)
                        role_changes_msg.append(f"分會: {new_branch}")

        await interaction.response.send_message(
            f"✅ **成功修改並替換成員資料！**\n"
            f"• 成員：{member.mention if member else f'<@{self.target_discord_id}>'}\n"
            f"• 原遊戲角色 ID：`{old_char_name}`\n"
            f"• 新遊戲角色 ID：`{new_char_name}`\n"
            f"• 新職業：`{new_class}`\n"
            f"• 新分會：`{new_branch}`\n"
            f"• 📁 試算表同步：{'成功' if sheet_updated else '未在試算表中找到該 Discord ID'}\n"
            f"• 🛡️ 身分組異動：{', '.join(role_changes_msg) if role_changes_msg else '無需調整'}",
            ephemeral=True
        )

class EditMemberCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="修改成員資料",
        description="【幹部專用】直接點選或標註成員，線上修改並更新其遊戲角色、職業與分會"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    async def edit_member(self, interaction: discord.Interaction, member: discord.Member):
        target_id_int = member.id
        target_id_str = str(target_id_int)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 🛡️ 雙重保險查詢：支援數字與文字欄位比對
        cursor.execute("""
            SELECT discord_id, discord_name, game_name, character_name, main_class, branch 
            FROM game_characters 
            WHERE discord_id = ? OR CAST(discord_id AS TEXT) = ?
        """, (target_id_int, target_id_str))
        
        row = cursor.fetchone()
        conn.close()

        if not row:
            await interaction.response.send_message(f"❌ 找不到成員 {member.mention} 在資料庫中的記錄！", ephemeral=True)
            return

        modal = EditMemberByDiscordModal(target_discord_id=target_id_int, db_data=row)
        await interaction.response.send_modal(modal)

async def setup(bot):
    await bot.add_cog(EditMemberCog(bot))
