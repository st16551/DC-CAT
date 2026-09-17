import aiohttp
import sqlite3
import discord
from discord.ext import commands, tasks
from datetime import datetime

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

            # 假設 API 回傳的結構包含 listings 或 items 陣列 (依實際 JSON 結構微調)
            listings = data.get("listings", data.get("data", []))
            if not listings:
                return

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

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            count = 0
            for item in listings:
                # 欄位名稱依 API 實際回傳格式為主 (例如 item_name / price)
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
            print(f"✅ 成功同步 ValeMarket 資料，共更新 {count 

} 筆市場行情！")

        except Exception as e:
            print(f"❌ ValeMarket 自動同步發生錯誤：{e}")

    @sync_market_data.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ValeMarketSync(bot))
