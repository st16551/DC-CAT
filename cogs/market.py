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
        self.ensure_db()

    # [升級防呆] 確保資料庫與表格隨時存在，絕不因缺表報錯
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

    # 24小時背景爬蟲：監聽 3 個交易頻道
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id in self.target_channel_ids:
            content = message.content
            parsed_items = self.parse_market_message(content)
            
            if parsed_items:
                self.ensure_db()
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

    # [全新升級] 自動掃描所有指定交易頻道，一鍵同步全部歷史行情
    @app_commands.command(name="同步歷史行情", description="[管理員專用] 自動掃描所有指定交易頻道的歷史對話，建立市場行情資料庫")
    @app_commands.describe(抓取數量="每個頻道要往上抓取幾則歷史訊息 (預設1000)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_market_history(self, interaction: discord.Interaction, 抓取數量: int = 1000):
        await interaction.response.defer(ephemeral=True)
        self.ensure_db()
        
        conn = sqlite3.connect("guild_system.db")
        cursor = conn.cursor()
        
        total_count = 0
        success_channels = 0

        # 自動遍歷所有設定好的目標頻道 ID
        for channel_id in self.target_channel_ids:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue
            
            if channel:
                success_channels += 1
                async for msg in channel.history(limit=抓取數量):
                    if msg.author.bot: 
                        continue
                    parsed_items = self.parse_market_message(msg.content)
                    if parsed_items:
                        for item in parsed_items:
                            cursor.execute("""
                                INSERT INTO market_prices (channel_id, raw_content, item_name, price, timestamp)
                                VALUES (?, ?, ?, ?, ?)
                            """, (str(channel.id), msg.content, item["item"], item["price"], msg.created_at.isoformat()))
                            total_count += 1
                            
        conn.commit()
        conn.close()
        
        await interaction.followup.send(
            f"✅ 歷史行情同步完成！已成功從 **{success_channels} 個指定交易頻道** 中，總共抓取 **{total_count}** 筆交易紀錄並寫入資料庫！", 
            ephemeral=True
        )

    @sync_market_error_handler if 'sync_market_error_handler' in globals() else None # 保持簡潔的錯誤處理
    @app_commands.command(name="sync_market_history_error") # 佔位避免裝飾器衝突，使用下方標準 error 處理
    async def dummy_err(self, interaction: discord.Interaction): pass

    @sync_market_history.error
    async def sync_market_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("❌ 你沒有權限使用這個指令（需要伺服器管理員權限）。", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 發生錯誤: {error}", ephemeral=True)

    # 中文 Slash 指令：查詢市場行情
    @app_commands.command(name="市場查詢", description="查詢指定道具的市場最新行情與平均價")
    @app_commands.describe(關鍵字="輸入要查詢的物品名稱關鍵字（例如：HEART GEM）")
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
