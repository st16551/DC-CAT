import sqlite3
import discord
from discord.ext import commands
from discord import app_commands

# 1. 點擊「市場查詢」跳出的彈出視窗
class MarketSearchModal(discord.ui.Modal, title="市場行情快速查詢"):
    def __init__(self):
        super().__init__()

    物品關鍵字 = discord.ui.TextInput(
        label="請輸入要查詢的道具關鍵字",
        placeholder="例如: 狂戰卡、魔防寶石、心之石...",
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        keyword = self.物品關鍵字.value.strip()
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT item_name, price, timestamp FROM market_prices 
            WHERE item_name LIKE ? ORDER BY timestamp DESC LIMIT 5
        """, (f"%{keyword}%",))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message(f"🔍 找不到與「`{keyword}`」相關的市場行情紀錄。", ephemeral=True)
            return

        embed = discord.Embed(title=f"📈 「{keyword}」市場行情查詢結果", color=discord.Color.blue())
        for r in rows:
            embed.add_field(
                name=f"🏷️ {r[0]}",
                value=f"💰 價格: **{r[1]:,}** 元\n📅 時間: {r[2]}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# 2. 包含 5 大功能的終極常駐面板 View
class GuildPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 永久有效，重啟不失效

    @discord.ui.button(label="🔍 市場查詢", style=discord.ButtonStyle.green, custom_id="guild_panel:market", row=0)
    async def market_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MarketSearchModal())

    @discord.ui.button(label="📦 登記打寶", style=discord.ButtonStyle.blurple, custom_id="guild_panel:split", row=0)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.split import SplitModal
        await interaction.response.send_modal(SplitModal())

    @discord.ui.button(label="📦 待售寶物庫", style=discord.ButtonStyle.gray, custom_id="guild_panel:pending", row=1)
    async def pending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, leader, item_name FROM splits WHERE status = 'pending'")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message("📦 目前沒有任何待售中的寶物。", ephemeral=True)
            return

        embed = discord.Embed(title="📦 待售寶物庫 (尚未售出)", color=discord.Color.gold())
        for r in rows:
            embed.add_field(name=f"編號 #{r[0]} | {r[3]}", value=f"📅 打寶日期: {r[1]} | 👑 負責人: {r[2]}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💰 我的未領查詢", style=discord.ButtonStyle.gray, custom_id="guild_panel:claims", row=1)
    async def claims_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            claim_text += f"• **{r[1]}** - `{r[2]:,} 元` *(負責人: {r[3]})*\n"
        
        embed.add_field(name="📜 明細列表", value=claim_text, inline=False)
        embed.add_field(name="⚠️ 領款安全提醒", value="領錢一律開**本尊**交易，切勿開小號分身；金額較大請自備精煉過裝備，避免不平等交易遭鎖帳號。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 分錢流水帳", style=discord.ButtonStyle.gray, custom_id="guild_panel:ledger", row=2)
    async def ledger_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            status_str = "🟢 進行中" if r[6] == 'active' else "🟡 待售中"
            embed.add_field(
                name=f"#{r[0]} | {r[3]} ({status_str})",
                value=f"📅 日期: {r[1]} | 👑 負責人: {r[2]} | 💰 總額: {r[4]:,}元 | 👥 每人拿: {r[5]:,}元",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class GuildManageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(GuildPanelView())

    @app_commands.command(name="架設公會面板", description="[管理員專用] 在當前頻道生成公會專屬五合一控制面板")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ 靈谷公會自動化管理中心",
            description="歡迎來到靈谷公會！本公會系統已全面自動化，請直接點擊下方按鈕進行各項操作：\n\n"
                        "• **🔍 市場查詢**：點擊輸入關鍵字，隨時查詢最新成交價格。\n"
                        "• **📦 登記打寶**：開啟表單登錄寶物、自動帶入名冊與計算分錢。\n"
                        "• **📦 待售寶物庫**：查看倉庫裡目前還沒賣掉的道具清單。\n"
                        "• **💰 我的未領查詢**：個人帳務面板，隨時查看未領款項與防詐提醒。\n"
                        "• **📊 分錢流水帳**：檢視目前公會所有的開單進度與均分金額。",
            color=discord.Color.dark_theme()
        )
        embed.set_footer(text="SpiritVale Guild Management System • All-in-One Panel")

        view = GuildPanelView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 成功在當前頻道架設五合一公會控制面板！", ephemeral=True)

    @setup_panel.error
    async def setup_panel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("❌ 你沒有權限使用這個指令（需要伺服器管理員權限）。", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 發生錯誤: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(GuildManageCog(bot))
