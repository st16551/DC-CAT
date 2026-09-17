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
        # 防呆建表
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
