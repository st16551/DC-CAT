import sqlite3
import re
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel_ids = {
            1526236280323702864,
            1534221564130627644,
            1529737907839959150
        }

    # 24小時背景爬蟲：監聽 3 個交易頻道
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id in self.target_channel_ids:
            content = message.content
            parsed_items = self.parse_market_message(content)
            
            if parsed_items:
                conn = sqlite3.connect("guild_system.db")
                cursor = conn.cursor()
                now_str = datetime.now().isoformat()
                
                for item in parsed_items:
                    cursor.execute("""
                        INSERT INTO market_prices (channel_id, raw_content, item_name, price, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (str(message.channel.id), content, item["item"], item["price"], now_str))
                
                conn.commit()
                conn.close()
                print(f"📈 [市場紀錄] 成功抓取並入庫: {parsed_items}")

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

    # 中文 Slash 指令：查詢市場行情
    @app_commands.command(name="市場查詢", description="查詢指定道具的市場最新行情與平均價")
    @app_commands.describe(關鍵字="輸入要查詢的物品名稱關鍵字（例如：HEART GEM）")
    async def market_search(self, interaction: discord.Interaction, 關鍵字: str):
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
        avg_price = sum(prices) // len(prices)
        
        embed.add_field(name="💰 近期平均行情", value=f"`{avg_price:,} 元`", inline=False)
        
        history_text = ""
        for r in rows:
            time_short = r[2].replace("T", " ")[:16]
            history_text += f"• **{r[0]}** - ` {r[1]:,} 元` *({time_short})*\n"
        
        embed.add_field(name="📜 最近成交紀錄", value=history_text, inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(MarketCog(bot))
