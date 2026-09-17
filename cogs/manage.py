import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# 1. 待售寶物庫：點擊後可一鍵「標記售出並結算」的介面
class SellPendingModal(discord.ui.Modal, title="將待售寶物標記為已售出"):
    def __init__(self, record_id, item_name):
        super().__init__()
        self.record_id = record_id
        self.item_name = item_name

    sold_price = discord.ui.TextInput(
        label="請輸入實際成交總金額 (數字)",
        placeholder="例如：150000000",
        required=True,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.sold_price.value.replace(",", "").replace("_", ""))
        except ValueError:
            await interaction.response.send_message("❌ 金額必須是純數字！", ephemeral=True)
            return

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            # 取得該筆寶物的負責人
            cursor.execute("SELECT leader FROM splits WHERE id = ?", (self.record_id,))
            res = cursor.fetchone()
            if not res:
                conn.close()
                await interaction.response.send_message("❌ 找不到此筆寶物紀錄！", ephemeral=True)
                return
            
            leader_name = res[0]

            # 取得參與分錢的成員名單
            cursor.execute("SELECT member_name FROM split_records WHERE leader_name = ? AND item_name = ?", (leader_name, self.item_name))
            members = [row[0] for row in cursor.fetchall()]
            
            if not members:
                members = [leader_name] # 預防萬一若無名單則算給負責人

            per_person = price // len(members)

            # 更新 splits 與 split_records
            cursor.execute(
                "UPDATE splits SET total_price = ?, per_person = ?, status = 'active' WHERE id = ?",
                (price, per_person, self.record_id)
            )
            cursor.execute(
                "UPDATE split_records SET total_per_person = ?, status = 0 WHERE leader_name = ? AND item_name = ?",
                (per_person, leader_name, self.item_name)
            )
            conn.commit()
            conn.close()

            await interaction.response.send_message(
                f"✅ **{self.item_name}** 已成功標記售出！總金額 `{price:,}` 元已自動均分給 `{len(members)}` 位成員（每人 `{per_person:,}` 元），已同步至個人未領查詢與流水帳！",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 結算失敗：{e}", ephemeral=True)


class PendingSelectView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=120)
        self.add_item(PendingSelect(rows))

class PendingSelect(discord.ui.Select):
    def __init__(self, rows):
        options = []
        for r in rows:
            # r = (id, date, leader, item_name)
            options.append(discord.SelectOption(
                label=f"#{r[0]} - {r[3][:80]}",
                description=f"負責人: {r[2]} | 日期: {r[1]}",
                value=str(r[0])
            ))
        super().__init__(placeholder="請選擇要結算售出或查看的待售寶物...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        record_id = int(self.values[0])
        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT item_name FROM splits WHERE id = ?", (record_id,))
        res = cursor.fetchone()
        conn.close()

        if not res:
            await interaction.response.send_message("❌ 找不到此寶物資料。", ephemeral=True)
            return

        await interaction.response.send_modal(SellPendingModal(record_id, res[0]))


# 2. 市場查詢彈出視窗
class MarketSearchModal(discord.ui.Modal, title="市場行情快速查詢"):
    物品關鍵字 = discord.ui.TextInput(
        label="請輸入要查詢的道具關鍵字",
        placeholder="例如: 狂戰卡、魔防寶石...",
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
            await interaction.response.send_message(f"❌ 查詢失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message(f"🔍 找不到與「`{keyword}`」相關的市場行情紀錄。", ephemeral=True)
            return

        embed = discord.Embed(title=f"📈 「{keyword}」市場行情查詢結果", color=discord.Color.blue())
        for r in rows:
            embed.add_field(name=f"🏷️ {r[0]}", value=f"💰 價格: **{r[1]:,}** 元\n📅 時間: {r[2]}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# 3. 五合一常駐面板 View
class GuildPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔍 市場查詢", style=discord.ButtonStyle.green, custom_id="guild_panel:market", row=0)
    async def market_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MarketSearchModal())

    @discord.ui.button(label="⚡ 即時分錢", style=discord.ButtonStyle.blurple, custom_id="guild_panel:split", row=0)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            from cogs.split import SplitModal
            await interaction.response.send_modal(SplitModal())
        except ImportError:
            await interaction.response.send_message("❌ 載入分錢模組失敗。", ephemeral=True)

    @discord.ui.button(label="📦 待售寶物庫", style=discord.ButtonStyle.gray, custom_id="guild_panel:pending", row=1)
    async def pending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT id, date, leader, item_name FROM splits WHERE status = 'pending'")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 讀取失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message("📦 目前倉庫沒有任何待售中的寶物。", ephemeral=True)
            return

        embed = discord.Embed(title="📦 待售寶物庫 (點擊下方選單可一鍵結算售出)", color=discord.Color.gold())
        for r in rows:
            embed.add_field(name=f"編號 #{r[0]} | {r[3]}", value=f"📅 日期: {r[1]} | 👑 負責人: {r[2]}", inline=False)
        
        view = PendingSelectView(rows)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="💰 我的未領查詢", style=discord.ButtonStyle.gray, custom_id="guild_panel:claims", row=1)
    async def claims_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member_name = interaction.user.display_name
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT item_name, total_per_person, leader_name 
                FROM split_records 
                WHERE member_name LIKE ? AND status = 0 AND total_per_person > 0
            """, (f"%{member_name}%",))
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 查詢失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message(f"🎉 太棒了 {member_name}！你目前沒有任何未領取的款項。", ephemeral=True)
            return

        total_unclaimed = sum([r[1] for r in rows])
        embed = discord.Embed(title=f"💰 「{member_name}」的未領金額清單", color=discord.Color.orange())
        embed.add_field(name="💎 總未領金額", value=f"`{total_unclaimed:,} 元`", inline=False)
        
        claim_text = "".join([f"• **{r[0]}** - `{r[1]:,} 元` *(負責人: {r[2]})*\n" for r in rows])
        embed.add_field(name="📜 明細列表", value=claim_text, inline=False)
        embed.add_field(name="⚠️ 領款安全提醒", value="領錢一律開本尊交易，切勿開小號分身。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 分錢流水帳", style=discord.ButtonStyle.gray, custom_id="guild_panel:ledger", row=2)
    async def ledger_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT id, date, leader, item_name, total_price, per_person, status FROM splits ORDER BY id DESC LIMIT 10")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 讀取流水帳失敗：{e}", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message("📜 目前沒有任何流水帳紀錄。", ephemeral=True)
            return

        embed = discord.Embed(title="📊 公會近期分錢與打寶流水帳 (最近10筆)", color=discord.Color.blue())
        for r in rows:
            status_map = {'active': '🟢 進行中', 'pending': '🟡 待售中', 'archived': '灰色 己封存'}
            status_str = status_map.get(r[6], r[6])
            embed.add_field(
                name=f"#{r[0]} | {r[3]} ({status_str})",
                value=f"📅 {r[1]} | 👑 負責人: {r[2]} | 💰 總額: {r[4]:,}元 | 👥 每人: {r[5]:,}元",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class GuildManageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(GuildPanelView())

    @app_commands.command(name="架設公會面板", description="[管理員專用] 生成五合一控制面板")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ 靈谷公會自動化管理中心",
            description="歡迎來到靈谷公會！請點擊下方按鈕操作：\n\n"
                        "• **🔍 市場查詢**：查詢最新成交價格。\n"
                        "• **⚡ 即時分錢**：開啟即時分錢與打寶登錄表單。\n"
                        "• **📦 待售寶物庫**：檢視倉庫未售出道具，點擊可一鍵結算售出！\n"
                        "• **💰 我的未領查詢**：個人未領款項與防詐提醒。\n"
                        "• **📊 分錢流水帳**：檢視近期公會所有財務流水。",
            color=discord.Color.dark_theme()
        )
        view = GuildPanelView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 成功架設面板！", ephemeral=True)

    @app_commands.command(name="未領查詢", description="查詢未領金額")
    async def my_claims_cmd(self, interaction: discord.Interaction):
        # 覆用 claims_button 邏輯或獨立指令
        member_name = interaction.user.display_name
        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT item_name, total_per_person, leader_name FROM split_records WHERE member_name LIKE ? AND status = 0 AND total_per_person > 0", (f"%{member_name}%",))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            await interaction.response.send_message(f"🎉 {member_name} 目前沒有未領款項。", ephemeral=True)
            return
        total = sum([r[1] for r in rows])
        await interaction.response.send_message(f"💎 總未領金額: `{total:,} 元`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(GuildManageCog(bot))
