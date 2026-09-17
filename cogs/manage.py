import sqlite3
import discord
from discord.ext import commands
from discord import app_commands

class GuildManageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 03. 待售寶物庫查詢
    @app_commands.command(name="待售寶物", description="查看目前尚未售出、還在倉庫裡的打寶品清單")
    async def pending_list(self, interaction: discord.Interaction):
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, leader, item_name, members FROM splits WHERE status = 'pending'")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message("📦 目前沒有任何待售中的寶物。", ephemeral=True)
            return

        embed = discord.Embed(title="📦 待售寶物庫 (尚未售出)", color=discord.Color.gold())
        for r in rows:
            embed.add_field(name=f"編號 #{r[0]} | {r[3]}", value=f"📅 打寶日期: {r[1]} | 👑 負責人: {r[2]}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # 04. 未領金額查詢 (`/未領查詢`)
    @app_commands.command(name="未領查詢", description="查詢自己目前還有多少打寶未領金額")
    async def my_claims(self, interaction: discord.Interaction):
        member_name = interaction.user.display_name
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, s.item_name, c.amount, s.leader 
            FROM claims c JOIN splits s ON c.split_id = s.id 
            WHERE c.member_name LIKE ? AND c.status = 'unclaimed'
        """, (f"%{member_name}%",))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message(f"🎉 太棒了 {member_name}！你目前沒有任何未領取的打寶款項。", ephemeral=True)
            return

        total_unclaimed = sum([r[2] for r in rows])
        embed = discord.Embed(title=f"💰 「{member_name}」的未領金額清單", color=discord.Color.orange())
        embed.add_field(name="💎 總未領金額", value=f"`{total_unclaimed:,} 元`", inline=False)
        
        claim_text = ""
        for r in rows:
            claim_text += f"• **{r[1]}** - ` {r[2]:,} 元` *(負責人: {r[3]})*\n"
        
        embed.add_field(name="📜 明細列表", value=claim_text, inline=False)
        embed.add_field(name="⚠️ 領款安全提醒", value="領錢一律開**本尊**交易，切勿開小號分身；金額較大請自備精煉過裝備，避免不平等交易遭鎖帳號。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=False)

    # 05. 即時分錢與歷史清單 (`/分錢清單`)
    @app_commands.command(name="分錢清單", description="查看所有開單分錢清單與領取進度")
    async def ledger_list(self, interaction: discord.Interaction):
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, leader, item_name, total_price, per_person, status FROM splits WHERE status != 'archived'")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message("📜 目前沒有進行中的分錢清單。", ephemeral=True)
            return

        embed = discord.Embed(title="📊 公會即時分錢與打寶清單", color=discord.Color.blue())
        for r in rows:
            status_str = "🟢 進行中/分錢中" if r[6] == 'active' else "🟡 待售中"
            embed.add_field(
                name=f"#{r[0]} | {r[3]} ({status_str})",
                value=f"📅 日期: {r[1]} | 👑 負責人: {r[2]} | 💰 總額: {r[4]:,}元 | 👥 每人拿: {r[5]:,}元",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot):
    await bot.add_cog(GuildManageCog(bot))
