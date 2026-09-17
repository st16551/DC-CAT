import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

class SplitModal(discord.ui.Modal, title="登記打寶與開單分錢"):
    def __init__(self, default_item: str = "", default_price: str = "0", roster_members: list = None):
        super().__init__()
        self.drop_item = default_item
        self.drop_price = default_price
        self.roster_members = roster_members or []

        # 動態設定欄位預設值
        self.掉落物品.default = default_item
        self.售出總金額.default = default_price

    打寶日期 = discord.ui.TextInput(
        label="打寶日期 (例如: 2026-09-18)",
        placeholder="請輸入日期...",
        default=datetime.now().strftime("%Y-%m-%d"),
        max_length=20
    )
    掉落物品 = discord.ui.TextInput(
        label="掉落的物品名稱（支援關鍵字）",
        placeholder="例如: 狂戰卡、魔防寶石...",
        max_length=100
    )
    售出總金額 = discord.ui.TextInput(
        label="售出總金額 (若尚未售出可填 0)",
        placeholder="例如: 200000000",
        max_length=20
    )
    參與成員關鍵字 = discord.ui.TextInput(
        label="參與成員 (輸入關鍵字或留空)",
        placeholder="例如: 小修, 鈴嚐, 或是留空從名冊選",
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            total_price = int(self.售出總金額.value.replace(",", ""))
        except ValueError:
            await interaction.response.send_message("❌ 金額格式錯誤，請輸入純數字！", ephemeral=True)
            return

        item_name = self.掉落物品.value
        keyword_input = self.參與成員關鍵字.value.strip()

        # 從資料庫撈取公會名冊進行比對或關鍵字過濾
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("SELECT member_name FROM roster")
        all_roster = [row[0] for row in cursor.fetchall()]
        conn.close()

        # 篩選參與人員
        selected_members = []
        if keyword_input:
            # 如果有輸入關鍵字，比對名冊中包含該關鍵字的成員
            keywords = [k.strip() for k in keyword_input.replace("，", ",").split(",")]
            for member in all_roster:
                if any(kw in member for kw in keywords):
                    selected_members.append(member)
            # 如果關鍵字沒對到名冊，就直接把輸入的字串當作名單切開
            if not selected_members:
                selected_members = keywords
        else:
            # 沒輸入就預設帶入全體名冊或保持空值由後續按鈕選擇
            selected_members = all_roster

        member_count = len(selected_members) if selected_members else 1
        per_person = total_price // member_count if member_count > 0 else 0

        embed = discord.Embed(title="📦 打寶紀錄建立成功", color=discord.Color.green())
        embed.add_field(name="📅 日期", value=self.打寶日期.value, inline=True)
        embed.add_field(name="👑 負責人", value=interaction.user.display_name, inline=True)
        embed.add_field(name="🏷️ 物品", value=item_name, inline=False)
        embed.add_field(name="💰 售出總額", value=f"{total_price:,} 元", inline=True)
        embed.add_field(name="👥 參與人數", value=f"{member_count} 人", inline=True)
        embed.add_field(name="💸 每人平分實拿", value=f"`{per_person:,} 元`", inline=False)
        
        members_str = ", ".join(selected_members) if selected_members else "尚未指定（可於後續調整）"
        if len(members_str) > 1024:
            members_str = members_str[:1000] + "..."
        embed.add_field(name="📝 參與成員名單", value=members_str, inline=False)

        view = SplitActionView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


class SplitActionView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

    @discord.ui.button(label="❌ 取消此筆登記", style=discord.ButtonStyle.danger)
    async def cancel_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有開單負責人或管理員才能取消此筆紀錄！", ephemeral=True)
            return
        
        await interaction.message.delete()
        await interaction.response.send_message("🗑️ 已經成功取消並刪除此筆打寶登記。", ephemeral=True)


class SplitCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="登記打寶", description="開啟表單登記打寶掉落物並自動從名冊帶入成員計算分錢")
    @app_commands.describe(物品關鍵字="選填：輸入物品關鍵字自動帶入行情價格與名稱")
    async def split_command(self, interaction: discord.Interaction, 物品關鍵字: str = None):
        default_item = ""
        default_price = "0"

        if 物品關鍵字:
            conn = sqlite3.connect("guild_system.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT item_name, price FROM market_prices 
                WHERE item_name LIKE ? ORDER BY timestamp DESC LIMIT 1
            """, (f"%{物品關鍵字}%",))
            row = cursor.fetchone()
            conn.close()

            if row:
                default_item = row[0]
                default_price = str(row[1])
            else:
                default_item = 物品關鍵字

        await interaction.response.send_modal(SplitModal(default_item=default_item, default_price=default_price))

async def setup(bot):
    await bot.add_cog(SplitCog(bot))
