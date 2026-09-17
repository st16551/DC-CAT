import sqlite3
import re
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Firebase 即時資料庫的公開 JSON 端點
        self.firebase_url = "https://index-c18db-default-rtdb.firebaseio.com/.json"
        self.ensure_db()

    # 確保資料庫與表格隨時存在，絕不因缺表報錯
    def ensure_db(self):
        conn = sqlite3.connect("guild_system.db")
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

    def parse_market_message(self, text):
        results = []
        pattern = r"([A-Z\u4e00-\u9fa5\s\+\d]+?)\s+(\d+(?:\.\d+)?)\s*([Mm萬gG])"
        matches = re.findall(pattern, text)
        
        for match in matches:
            item_name = match[0].strip()
            raw_price = float(match[1])
            unit = match[2].lower()
            
            multiplier = 1000000 if unit in ["m", "萬"] else 1
            price = int(raw_price * multiplier)
            
            results.append({"item": item_name, "price": price})
        return results

    # 一鍵直接從 Firebase 雲端資料庫同步所有市場行情
    @app_commands.command(name="同步歷史行情", description="[管理員專用] 直接從雲端市場資料庫同步最新行情資料")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_market_history(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.ensure_db()
        
        total_count = 0
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.firebase_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ 無法連線至雲端資料庫，狀態碼: {resp.status}", ephemeral=True)
                        return
                    data = await resp.json()
        except Exception as e:
            await interaction.followup.send(f"❌ 讀取雲端資料發生錯誤: {e}", ephemeral=True)
            return

        if not data or not isinstance(data, dict):
            await interaction.followup.send("⚠️ 雲端資料庫格式不符或目前沒有回傳資料。", ephemeral=True)
            return

        # 抓取 discord_market 底下的清單
        market_list = data.get("discord_market", [])
        if not market_list:
            await interaction.followup.send("⚠️ 雲端資料庫中找不到 `discord_market` 節點資料。", ephemeral=True)
            return

        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()

        for entry in market_list:
            if not isinstance(entry, dict):
                continue
            
            # 優先使用 combined欄位，如果沒有則退而求其次找 title
            content = entry.get("combined") or entry.get("title")
            if content and isinstance(content, str):
                parsed_items = self.parse_market_message(content)
                # 如果正規表達式沒抓到金額，但 Firebase 欄位本身有記錄 price 且大於 0，也可以手動納入
                raw_price = entry.get("price", 0)
                
                if parsed_items:
                    timestamp = entry.get("time") or datetime.now().isoformat()
                    channel_id = str(entry.get("channel_id", "firebase_sync"))
                    for item in parsed_items:
                        cursor.execute("""
                            INSERT INTO market_prices (channel_id, raw_content, item_name, price, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                        """, (channel_id, content, item["item"], item["price"], str(timestamp)))
                        total_count += 1
                elif raw_price > 0:
                    # 如果內文沒抓到價格但資料本身有 price 欄位，直接以標題作為物品名稱入庫
                    timestamp = entry.get("time") or datetime.now().isoformat()
                    channel_id = str(entry.get("channel_id", "firebase_sync"))
                    cursor.execute("""
                        INSERT INTO market_prices (channel_id, raw_content, item_name, price, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (channel_id, content, content[:30], int(raw_price), str(timestamp)))
                    total_count += 1

        conn.commit()
        conn.close()
        
        await interaction.followup.send(
            f"✅ 雲端市場行情同步完成！已成功從遠端 `discord_market` 匯入 **{total_count}** 筆交易紀錄至本機資料庫！", 
            ephemeral=True
        )

    @sync_market_history.error
    async def sync_market_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("❌ 你沒有權限使用這個指令（需要伺服器管理員權限）。", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 發生錯誤: {error}", ephemeral=True)

    # 市場查詢指令
    @app_commands.command(name="市場查詢", description="查詢指定道具的市場最新行情與平均價")
    @app_commands.describe(關鍵字="輸入要查詢的物品名稱關鍵字（例如：Echo）")
    async def market_search(self, interaction: discord.Interaction, 關鍵字: str):
        self.ensure_db()
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT item_name, price, timestamp FROM market_prices 
            WHERE item_name LIKE ? ORDER BY timestamp DESC LIMIT 5
        """, (f"%{關鍵字}%",))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            await interaction.response.send_message(f"❌ 找不到與 **{關鍵字}** 相關的市場行情紀錄。", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"📊 「{關鍵字}」市場行情搜尋結果", color=discord.Color.blue())
        prices = [row[1] for row in rows]
        avg_price = sum(prices) // len(prices) if prices else 0
        
        embed.add_field(name="💰 近期平均行情", value=f"`{avg_price:,} 元`", inline=False)
        
        history_text = ""
        for r in rows:
            time_short = r[2].replace("T", " ")[:16] if r[2] else "未知時間"
            history_text += f"• **{r[0]}** - ` {r[1]:,} 元` *({time_short})*\n"
        
        embed.add_field(name="📜 最近成交紀錄", value=history_text, inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(MarketCog(bot))
