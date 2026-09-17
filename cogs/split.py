import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

class SplitModal(discord.ui.Modal, title="登記打寶與開單分錢"):
    def __init__(self, default_item: str = "", default_price: str = "0"):
        super().__init__()
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
        label="售出總金額 (若尚未售出填 0)",
        placeholder="例如: 200000000",
        max_length=20
    )
    參與成員關鍵字 = discord.ui.TextInput(
        label="參與成員 (輸入關鍵字或留空帶入全名冊)",
        placeholder="例如: 小修, 鈴嚐",
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

        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("SELECT member_name FROM roster")
        all_roster = [row[0] for row in cursor.fetchall()]

        selected_members = []
        if keyword_input:
            keywords = [k.strip() for k in keyword_input.replace("，", ",").split(",")]
            for member in all_roster:
                if any(kw in member for kw in keywords):
                    selected_members.append(member)
            if not selected_members:
                selected_members = keywords
        else:
            selected_members = all_roster if all_roster else [interaction.user.display_name]

        member_count = len(selected_members)
        per_person = total_price // member_count if member_count > 0 else 0
        status = 'active' if total_price > 0 else 'pending' # 0元代表尚未售出，存入待售庫

        # 寫入資料庫
        cursor.execute("""
            INSERT INTO splits (date, leader, item_name, total_price, status, members, per_person)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (self.打寶日期.value, interaction.user.display_name, item_name, total_price, status, ",".join(selected_members), per_person))
        split_id = cursor.lastrowid

        # 若有價格，同步在 claims 表中生成每個人的未領紀錄
        if total_price > 0:
            for member in selected_members:
                cursor.execute("""
                    INSERT INTO claims (split_id, member_name, amount, status)
                    VALUES (?, ?, ?, ?)
                """, (split_id, member, per_person, 'unclaimed'))

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="📦 打寶紀錄建立成功" if total_price > 0 else "📦 物品已安全存入待售寶物庫",
            color=discord.Color.green() if total_price > 0 else discord.Color.gold()
        )
        embed.add_field(name="📅 日期", value=self.打寶日期.value, inline=True)
        embed.add_field(name="👑 負責人", value=interaction.user.display_name, inline=True)
        embed.add_field(name="🏷️ 物品", value=item_name, inline=False)
        embed.add_field(name="💰 售出總額", value=f"{total_price:,} 元" if total_price > 0 else "尚未售出 (待售中)", inline=True)
        embed.add_field(name="👥 參與人數", value=f"{member_count} 人", inline=True)
        if total_price > 0:
            embed.add_field(name="💸 每人平分實拿", value=f"`{per_person:,} 元`", inline=False)
        embed.add_field(name="📝 參與名單", value=", ".join(selected_members)[:1000], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=False)

class SplitCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="登記打寶", description="開啟表單登記打寶掉落物並自動計算分錢")
    @app_commands.describe(物品關鍵字="選填：輸入物品關鍵字自動帶入行情價格")
    async def split_command(self, interaction: discord.Interaction, 物品關鍵字: str = None):
        default_item = ""
        default_price = "0"
        if 物品關鍵字:
            conn = sqlite3.connect("guild_system.db")
            cursor = conn.cursor()
            cursor.execute("SELECT item_name, price FROM market_prices WHERE item_name LIKE ? ORDER BY timestamp DESC LIMIT 1", (f"%{物品關鍵字}%",))
            row = cursor.fetchone()
            conn.close()
            if row:
                default_item, default_price = row[0], str(row[1])
            else:
                default_item = 物品關鍵字

        await interaction.response.send_modal(SplitModal(default_item=default_item, default_price=default_price))

async def setup(bot):
    await bot.add_cog(SplitCog(bot))
