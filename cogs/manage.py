import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# 1. 市場查詢彈出視窗
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
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    raw_content TEXT,
                    item_name TEXT,
                    price INTEGER,
                    timestamp TEXT
                )
            """)
            cursor.execute("""
                SELECT item_name, price, timestamp FROM market_prices 
                WHERE item_name LIKE ? ORDER BY timestamp DESC LIMIT 5
            """, (f"%{keyword}%",))
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫時發生錯誤：{e}", ephemeral=True)
            return

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

# 2. 五合一常駐面板 View
class GuildPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔍 市場查詢", style=discord.ButtonStyle.green, custom_id="guild_panel:market", row=0)
    async def market_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MarketSearchModal())

    @discord.ui.button(label="📦 登記打寶", style=discord.ButtonStyle.blurple, custom_id="guild_panel:split", row=0)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            from cogs.split import SplitModal
            await interaction.response.send_modal(SplitModal())
        except ImportError:
            await interaction.response.send_message("❌ 尚未在 split.py 中定義 SplitModal，請確認該模組內容。", ephemeral=True)

    @discord.ui.button(label="📦 待售寶物庫", style=discord.ButtonStyle.gray, custom_id="guild_panel:pending", row=1)
    async def pending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS splits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    leader TEXT,
                    item_name TEXT,
                    total_price INTEGER,
                    per_person INTEGER,
                    status TEXT
                )
            """)
            cursor.execute("SELECT id, date, leader, item_name FROM splits WHERE status = 'pending'")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 讀取資料庫失敗：{e}", ephemeral=True)
            return

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
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            # 相容 split.py 的 split_records 資料表 (status = 0 代表未領)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS split_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_name TEXT,
                    item_name TEXT,
                    total_per_person INTEGER,
                    leader_name TEXT,
                    status INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                SELECT item_name, total_per_person, leader_name 
                FROM split_records 
                WHERE member_name LIKE ? AND status = 0
            """, (f"%{member_name}%",))
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢未領紀錄失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message(f"🎉 太棒了 {member_name}！你目前沒有任何未領取的打寶款項。", ephemeral=True)
            return

        total_unclaimed = sum([r[1] for r in rows])
        embed = discord.Embed(title=f"💰 「{member_name}」的未領金額清單", color=discord.Color.orange())
        embed.add_field(name="💎 總未領金額", value=f"`{total_unclaimed:,} 元`", inline=False)
        
        claim_text = ""
        for r in rows:
            claim_text += f"• **{r[0]}** - `{r[1]:,} 元` *(負責人: {r[2]})*\n"
        
        embed.add_field(name="📜 明細列表", value=claim_text, inline=False)
        embed.add_field(name="⚠️ 領款安全提醒", value="領錢一律開**本尊**交易，切勿開小號分身；金額較大請自備精煉過裝備，避免不平等交易遭鎖帳號。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 分錢流水帳", style=discord.ButtonStyle.gray, custom_id="guild_panel:ledger", row=2)
    async def ledger_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS splits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    leader TEXT,
                    item_name TEXT,
                    total_price INTEGER,
                    per_person INTEGER,
                    status TEXT
                )
            """)
            cursor.execute("SELECT id, date, leader, item_name, total_price, per_person, status FROM splits WHERE status != 'archived'")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 讀取流水帳失敗：{e}", ephemeral=True)
            return

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

    @app_commands.command(name="待售寶物", description="查看目前尚未售出、還在倉庫裡的打寶品清單")
    async def pending_list_cmd(self, interaction: discord.Interaction):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT id, date, leader, item_name FROM splits WHERE status = 'pending'")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 讀取資料失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message("📦 目前沒有任何待售中的寶物。", ephemeral=True)
            return

        embed = discord.Embed(title="📦 待售寶物庫 (尚未售出)", color=discord.Color.gold())
        for r in rows:
            embed.add_field(name=f"編號 #{r[0]} | {r[3]}", value=f"📅 打寶日期: {r[1]} | 👑 負責人: {r[2]}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="未領查詢", description="查詢自己目前還有多少打寶未領金額")
    async def my_claims_cmd(self, interaction: discord.Interaction):
        member_name = interaction.user.display_name
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT item_name, total_per_person, leader_name 
                FROM split_records 
                WHERE member_name LIKE ? AND status = 0
            """, (f"%{member_name}%",))
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢未領金額失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message(f"🎉 太棒了 {member_name}！你目前沒有任何未領取的打寶款項。", ephemeral=True)
            return

        total_unclaimed = sum([r[1] for r in rows])
        embed = discord.Embed(title=f"💰 「{member_name}」的未領金額清單", color=discord.Color.orange())
        embed.add_field(name="💎 總未領金額", value=f"`{total_unclaimed:,} 元`", inline=False)
        
        claim_text = ""
        for r in rows:
            claim_text += f"• **{r[0]}** - `{r[1]:,} 元` *(負責人: {r[2]})*\n"
        
        embed.add_field(name="📜 明細列表", value=claim_text, inline=False)
        embed.add_field(name="⚠️ 領款安全提醒", value="領錢一律開**本尊**交易，切勿開小號分身；金額較大請自備精煉過裝備，避免不平等交易遭鎖帳號。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GuildManageCog(bot))
