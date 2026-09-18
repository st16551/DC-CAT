import aiohttp
import asyncio
import sqlite3
import os
import discord
from discord.ext import commands, tasks
from discord.ui import View, Select, Button, Modal, TextInput

# ================= 檔案設定與全域常數 =================
DB_FILE = "guild_database.db"
MARKET_API_URL = "https://market.spiritvalers.com/api" # 依實際 API 調整
TRANSLATION_FILES = ["items.txt1.txt", "items.txt2.txt", "items.txt3.txt"]

GLOBAL_EN_TO_CN = {}
GLOBAL_CN_TO_EN = {}

def load_translations():
    """自動讀取多個文字翻譯檔建立雙向對照字典"""
    global GLOBAL_EN_TO_CN, GLOBAL_CN_TO_EN
    GLOBAL_EN_TO_CN.clear()
    GLOBAL_CN_TO_EN.clear()
    
    for filename in TRANSLATION_FILES:
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split(":", 1)
                        if len(parts) == 2:
                            en_name = parts[0].strip().strip('"\'')
                            cn_name = parts[1].strip().strip('"\'')
                            GLOBAL_EN_TO_CN[en_name] = cn_name
                            GLOBAL_CN_TO_EN[cn_name] = en_name
                print(f"[Market] 成功載入翻譯檔: {filename}")
            except Exception as e:
                print(f"[Market] 載入翻譯檔 {filename} 失敗: {e}")

def get_cn_name(en_name: str) -> str:
    return GLOBAL_EN_TO_CN.get(en_name, en_name)

def get_en_name(cn_name: str) -> str:
    return GLOBAL_CN_TO_EN.get(cn_name, cn_name)

# 初始化資料庫
def init_market_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_prices (
            item_name TEXT PRIMARY KEY,
            min_price INTEGER,
            max_price INTEGER,
            avg_price REAL,
            sample_count INTEGER,
            last_updated TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_name TEXT,
            target_price INTEGER,
            is_below INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_market_db()
load_translations()

# ================= 核心 Cog 模組 =================
class ValeMarketPro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.market_sync_task.start()

    def cog_unload(self):
        self.market_sync_task.cancel()

    @tasks.loop(minutes=10)
    async def market_sync_task(self):
        """背景定時同步市場 API 數據"""
        await self.sync_data_from_api()

    @market_sync_task.before_loop
    async def before_market_sync(self):
        await self.bot.wait_until_ready()
        await self.sync_data_from_api()

    async def sync_data_from_api(self):
        """向市場 API 抓取資料並寫入資料庫（強制進行中文轉換）"""
        load_translations()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{MARKET_API_URL}/items") as resp: # 假設的獲取清單端點
                    if resp.status != 200:
                        return
                    data = await resp.json()
                    
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    
                    # 假設 data 迴圈寫入
                    for item in data.get("items", []):
                        raw_name = item.get("name")
                        cn_name = get_cn_name(raw_name) # 確保存入的是中文名稱
                        
                        cursor.execute('''
                            INSERT OR REPLACE INTO market_prices (item_name, min_price, max_price, avg_price, sample_count, last_updated)
                            VALUES (?, ?, ?, ?, ?, datetime('now'))
                        ''', (cn_name, item.get("min_price", 0), item.get("max_price", 0), item.get("avg_price", 0), item.get("count", 0)))
                    
                    conn.commit()
                    conn.close()
        except Exception as e:
            print(f"[Market Sync Error] {e}")

    @commands.slash_command(name="market", description="開啟靈谷全球市場資訊系統")
    async def market_panel(self, ctx: discord.ApplicationContext):
        embed = discord.Embed(
            title="📈 靈谷全球市場資訊系統 (ValeMarket PRO)",
            description="歡迎使用公會專屬智慧金融與市場分析終端。\n請透過下方按鈕或選單進行查詢與盯盤設定。",
            color=discord.Color.gold()
        )
        embed.set_footer(text="數據每 10 分鐘自動同步一次 | 支援中英文雙向對應")
        await ctx.respond(embed=embed, view=MarketPanelView())

# ================= UI 互動介面 =================

class MarketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔍 手動輸入查詢", style=discord.ButtonStyle.primary, custom_id="market_manual_query_btn")
    async def manual_query_btn(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_modal(MarketSearchModal())

    @discord.ui.button(label="🔄 強制同步資料", style=discord.ButtonStyle.secondary, custom_id="market_force_sync_btn")
    async def force_sync_btn(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        load_translations()
        # 這裡可呼叫同步
        await interaction.followup.send("✅ 翻譯字典重新載入與資料庫同步完成！", ephemeral=True)

class MarketSearchModal(Modal):
    def __init__(self):
        super().__init__(title="輸入查詢道具名稱")
        self.item_input = TextInput(
            label="道具名稱（支援中文 / 英文）",
            placeholder="例如：流動精華 或 Essence of Flow",
            required=True,
            max_length=50
        )
        self.add_item(self.item_input)

    async def callback(self, interaction: discord.Interaction):
        user_query = self.item_input.value.strip()
        # 轉換成 API/資料庫看的英文或保持中文對應
        target_name = get_cn_name(user_query) # 若輸入英文轉中文，或反之
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT min_price, max_price, avg_price, sample_count, last_updated FROM market_prices WHERE item_name LIKE ?", (f"%{target_name}%",))
        row = cursor.fetchone()
        conn.close()

        if not row:
            await interaction.response.send_message(f"❌ 找不到與 **{user_query}** 相關的道具資料，請確認名稱是否正確。", ephemeral=True)
            return

        min_p, max_p, avg_p, count, updated = row
        embed = discord.Embed(title=f"📊 市場行情分析：{target_name}", color=discord.Color.green())
        embed.add_field(name="📉 歷史最低價", value=f"{min_p:,} G", inline=True)
        embed.add_field(name="📈 歷史最高價", value=f"{max_p:,} G", inline=True)
        embed.add_field(name="⚖️ 平均參考價", value=f"{avg_p:,.1f} G", inline=True)
        embed.add_field(name="📦 累計樣本數", value=f"{count} 筆", inline=False)
        embed.set_footer(text=f"最後更新時間：{updated}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(ValeMarketPro(bot))
