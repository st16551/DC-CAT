import aiohttp
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime

# ===================== 資料庫初始化 =====================
def init_market_db():
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
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ 初始化市場資料庫失敗：{e}")

init_market_db()

# ===================== 查詢用的 Modal =====================
class MarketSearchModal(discord.ui.Modal, title="靈谷市場行情查詢"):
    search_keyword = discord.ui.TextInput(
        label="輸入道具名稱 (支援英文或關鍵字)",
        placeholder="例如：Sword / Ring / 靈石",
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        keyword = self.search_keyword.value.strip()
        
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            # 模糊搜尋並取最新 10 筆
            cursor.execute("""
                SELECT item_name, price, timestamp 
                FROM market_prices 
                WHERE item_name LIKE ? 
                ORDER BY id DESC LIMIT 10
            """, (f"%{keyword}%",))
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢資料庫失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message(f"🔍 找不到與 `"{keyword}"` 相關的市場行情，請確認名稱或英文拼寫是否正確！", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📈 查詢結果：{keyword}",
            description="以下為最近同步到的市場最新價格清單：",
            color=discord.Color.blue()
        )

        for item_name, price, timestamp in rows:
            embed.add_field(
                name=item_name,
                value=f"💰 價格：`{price:,}` G\n⏱️ 時間：{timestamp}",
                inline=False
            )
        
        embed.set_footer(text="靈谷全球市場資訊系統 (ValeMarket)")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ===================== 常駐面板的 View =====================
class MarketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 永久常駐按鈕

    @discord.ui.button(
        label="🔍 查詢道具價格", 
        style=discord.ButtonStyle.primary, 
        custom_id="persistent_market_search_btn"
    )
    async def search_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MarketSearchModal())


# ===================== 主 Cog (背景同步 + 面板指令) =====================
class ValeMarketSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_market_data.start()

    def cog_unload(self):
        self.sync_market_data.cancel()

    # 每 10 分鐘自動同步一次 ValeMarket 全球快照
    @tasks.loop(minutes=10)
    async def sync_market_data(self):
        url = "https://market-api.spiritvalers.com/v2/markets/global/snapshot"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status != 200:
                        print(f"⚠️ ValeMarket API 同步失敗，狀態碼: {resp.status}")
                        return
                    data = await resp.json()

            listings = data.get("listings", data.get("data", []))
            if not listings:
                return

            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            count = 0
            for item in listings:
                item_name = item.get("itemName", item.get("name", "Unknown"))
                price = int(item.get("price", item.get("unitPrice", 0)))
                
                if price > 0:
                    cursor.execute(
                        "INSERT INTO market_prices (channel_id, raw_content, item_name, price, timestamp) VALUES (?, ?, ?, ?, ?)",
                        ("ValeMarket_API", "Global Snapshot", item_name, price, now_str)
                    )
                    count += 1

            conn.commit()
            conn.close()
            print(f"✅ 成功同步 ValeMarket 資料，共更新 {count} 筆市場行情！")

        except Exception as e:
            print(f"❌ ValeMarket 自動同步發生錯誤：{e}")

    @sync_market_data.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    # 設置固定卡片的指令
    @app_commands.command(name="架設市場面板", description="在當前頻道架設一個常駐的靈谷全球市場查詢卡片")
    async def setup_market_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有伺服器管理員才能架設市場面板！", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 靈谷全球市場情報站 (ValeMarket)",
            description=(
                "歡迎使用公會專屬市場查詢系統！\n\n"
                "• 機器人每 **10 分鐘** 會自動同步一次全球市場最新快照。\n"
                "• 點擊下方按鈕即可輸入英文或關鍵字查詢道具即時價格。\n\n"
                "👉 **點擊下方按鈕開始查詢裝備與材料行情！**"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="小貓咪智能公會系統 • 數據定時更新中")

        view = MarketPanelView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 成功在當前頻道架設市場查詢常駐面板！", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ValeMarketSync(bot))
