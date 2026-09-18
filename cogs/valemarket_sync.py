from datetime import datetime
import sqlite3
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ===================== 資料庫初始化 =====================


def init_market_db():
    try:
        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()

        # 1. 市場歷史價格表
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

        # 2. 價格盯盤警報表 (加入 is_active 狀態控制)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                item_keyword TEXT,
                target_price INTEGER,
                alert_type TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ 初始化市場資料庫失敗：{e}")


init_market_db()


# ===================== 共用核心同步邏輯 (已強化單價與欄位對應) =====================
async def execute_market_sync(bot=None):
    """將 API 抓取與盯盤掃描抽離成獨立函數，精準對應遊戲市場 API 的 displayName 與 unitPrice"""
    url = "https://market-api.spiritvalers.com/v2/markets/global/snapshot"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    print(
                        f"⚠️ ValeMarket API 同步失敗，狀態碼: {resp.status}"
                    )
                    return False, f"API 狀態碼異常: {resp.status}"

                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    print(f"⚠️ 無法解析 JSON，原始回應: {text[:200]}")
                    return False, "API 回傳格式非合法 JSON"

        # 萬能結構解構
        raw_items = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            for key in ["listings", "data", "items", "result", "snapshot", "value"]:
                if key in data and isinstance(data[key], list):
                    raw_items = data[key]
                    break
            if not raw_items:
                for val in data.values():
                    if isinstance(val, list):
                        raw_items = val
                        break
            if not raw_items and ("displayName" in data or "itemId" in data or "name" in data):
                raw_items = [data]

        if not raw_items:
            print(f"⚠️ 無法從 API 結構中萃取清單，原始資料型態: {type(data)}")
            return False, "找不到有效的清單陣列"

        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        count = 0

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            # 💡 優先鎖定 displayName，其次才是其他備用名稱
            item_name = (
                item.get("displayName")
                or item.get("itemId")
                or item.get("name")
                or item.get("item_name")
                or item.get("itemName")
                or item.get("title")
                or "Unknown"
            )

            # 💡 優先鎖定 unitPrice，確保抓到的是正確的單價
            price_raw = (
                item.get("unitPrice")
                or item.get("unit_price")
                or item.get("price")
                or item.get("minPrice")
                or item.get("min_price")
                or 0
            )

            try:
                price = int(float(price_raw))  # 轉為整數價格
            except (ValueError, TypeError):
                price = 0

            if item_name != "Unknown" and price > 0:
                cursor.execute(
                    "INSERT INTO market_prices (channel_id, raw_content, item_name,"
                    " price, timestamp) VALUES (?, ?, ?, ?, ?)",
                    ("ValeMarket_API", "Global Snapshot", item_name, price, now_str),
                )
                count += 1

        conn.commit()

        # --- 🚀 價格盯盤自動掃描與通知機制 ---
        cursor.execute(
            "SELECT id, user_id, item_keyword, target_price, alert_type FROM"
            " market_alerts WHERE is_active = 1"
        )
        alerts = cursor.fetchall()

        for alert_id, user_id, keyword, target_price, alert_type in alerts:
            cursor.execute(
                """
                    SELECT item_name, price FROM market_prices 
                    WHERE item_name LIKE ? COLLATE NOCASE
                    ORDER BY id DESC LIMIT 1
                """,
                (f"%{keyword}%",),
            )
            latest = cursor.fetchone()

            if latest:
                matched_name, current_price = latest
                triggered = False
                if alert_type == "低於" and current_price <= target_price:
                    triggered = True
                elif alert_type == "高於" and current_price >= target_price:
                    triggered = True

                if triggered:
                    cursor.execute(
                        "UPDATE market_alerts SET is_active = 0 WHERE id = ?",
                        (alert_id,),
                    )
                    conn.commit()

                    if bot:
                        try:
                            user = await bot.fetch_user(int(user_id))
                            if user:
                                embed = discord.Embed(
                                    title="🚨 【靈谷市場盯盤觸發通知】",
                                    description=(
                                        f"您設定的價格警報已達成！\n\n• **道具名稱**："
                                        f" `{matched_name}`\n• **設定條件**：價格 {alert_type}"
                                        f" `{target_price:,} G`\n• **最新實價**：💰"
                                        f" `{current_price:,} G`\n\n*(此盯盤任務已自動完成並結案，如需繼續監控請重新設定)*"
                                    ),
                                    color=discord.Color.brand_red(),
                                )
                                await user.send(embed=embed)
                        except Exception as dm_err:
                            print(f"⚠️ 無法發送私訊給用戶 {user_id}: {dm_err}")

        conn.close()
        print(f"✅ 成功同步 ValeMarket 資料 ({count}筆)，並完成盯盤掃描！")
        return True, count
    except Exception as e:
        print(f"❌ ValeMarket 自動同步或盯盤發生錯誤：{e}")
        return False, str(e)


# ===================== 核心查詢共用邏輯 =====================
async def perform_market_search(interaction: discord.Interaction, keyword: str):
    search_pattern = f"%{keyword}%"
    try:
        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()

        cursor.execute(
            """
                SELECT item_name, price, timestamp 
                FROM market_prices 
                WHERE item_name LIKE ? COLLATE NOCASE
                ORDER BY id DESC LIMIT 20
            """,
            (search_pattern,),
        )
        rows = cursor.fetchall()

        cursor.execute(
            """
                SELECT MIN(price), MAX(price), AVG(price), COUNT(*) 
                FROM market_prices 
                WHERE item_name LIKE ? COLLATE NOCASE
            """,
            (search_pattern,),
        )
        stats = cursor.fetchone()
        conn.close()
    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ 查詢資料庫失敗：{e}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 查詢資料庫失敗：{e}", ephemeral=True)
        return

    if not rows:
        msg = f'🔍 找不到與 `"{keyword}"` 相關的市場行情，請確認名稱或英文拼寫是否正確！'
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return

    min_p, max_p, avg_p, total_count = (
        stats if stats and stats[3] > 0 else (0, 0, 0, 0)
    )
    avg_p = avg_p or 0

    embed = discord.Embed(
        title=f"📈 市場行情分析：{keyword}",
        description=(
            f"📊 **大數據統計摘要**：\n• 歷史最低價：`{min_p:,}` G\n• 歷史最高價："
            f" `{max_p:,}` G\n• 平均參考價：`{int(avg_p):,}` G\n• 累計樣本數："
            f" `{total_count}` 筆\n----------------------------------------"
        ),
        color=discord.Color.gold(),
    )

    history_text = ""
    for item_name, price, timestamp in rows[:5]:
        history_text += (
            f"• **{item_name}** | 💰 `{price:,}` G | ⏱️ `{timestamp}`\n"
        )

    embed.add_field(
        name="🕒 最近幾筆交易/上架紀錄",
        value=history_text if history_text else "無",
        inline=False,
    )
    embed.set_footer(text="靈谷全球市場資訊系統 (ValeMarket PRO)")

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ===================== 1. 深度查詢 Modal 與下拉選單介面 =====================
class MarketSearchModal(discord.ui.Modal, title="靈谷市場行情深度查詢"):
    search_keyword = discord.ui.TextInput(
        label="輸入道具名稱 (支援英文或關鍵字)",
        placeholder="例如：Sprite Card",
        required=True,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        keyword = self.search_keyword.value.strip()
        await perform_market_search(interaction, keyword)


class MarketItemSelect(discord.ui.Select):
    def __init__(self, popular_items):
        options = [
            discord.SelectOption(label=name[:100], value=name[:100])
            for name in popular_items
        ]
        if not options:
            options.append(
                discord.SelectOption(label="目前尚無熱門資料，請使用手動按鈕", value="none")
            )
        super().__init__(
            placeholder="⚡ 從近期熱門道具中選擇快速查詢...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message(
                "請點擊下方按鈕手動輸入關鍵字查詢！", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await perform_market_search(interaction, self.values[0])


class MarketSearchSelectView(discord.ui.View):
    def __init__(self, popular_items):
        super().__init__(timeout=60)
        self.add_item(MarketItemSelect(popular_items))

    @discord.ui.button(
        label="⌨️ 手動輸入關鍵字查詢",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def manual_search_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(MarketSearchModal())


# ===================== 2. 設定盯盤 Modal =====================
class MarketAlertModal(discord.ui.Modal, title="設定價格盯盤警報"):
    item_keyword = discord.ui.TextInput(
        label="欲盯盤的道具關鍵字 (英文/中文)",
        placeholder="例如：Sprite Card",
        required=True,
        max_length=50,
    )
    target_price = discord.ui.TextInput(
        label="目標價格 (數字)",
        placeholder="例如：50000",
        required=True,
        max_length=15,
    )
    alert_condition = discord.ui.TextInput(
        label="觸發條件 (填 '低於' 或 '高於')",
        placeholder="低於 或 高於",
        required=True,
        max_length=5,
    )

    async def on_submit(self, interaction: discord.Interaction):
        keyword = self.item_keyword.value.strip()
        cond = self.alert_condition.value.strip()

        if cond not in ["低於", "高於"]:
            await interaction.response.send_message(
                "❌ 觸發條件只能填寫 **『低於』** 或 **『高於』**！", ephemeral=True
            )
            return

        try:
            price = int(self.target_price.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ 目標價格必須是純數字！", ephemeral=True
            )
            return

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                    INSERT INTO market_alerts (user_id, item_keyword, target_price, alert_type, is_active, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    str(interaction.user.id),
                    keyword,
                    price,
                    cond,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 寫入資料庫失敗：{e}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔔 價格盯盤設定成功！",
            description=(
                f"• **追蹤道具**：`{keyword}`\n• **觸發條件**：當價格 **{cond}**"
                f" `{price:,} G` 時\n• **通知方式**：機器人將會透過 **私人訊息 (DM)**"
                " 通知您一次\n*(註：警報觸發後會自動失效，避免疲勞轟炸)*"
            ),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ===================== 3. 管理我的盯盤清單 View =====================
class CancelAlertSelect(discord.ui.Select):

    def __init__(self, alerts):
        options = []
        for alert_id, keyword, price, cond in alerts:
            options.append(
                discord.SelectOption(
                    label=f"ID:{alert_id} | {keyword}",
                    description=f"條件: {cond} {price:,} G",
                    value=str(alert_id),
                )
            )
        super().__init__(
            placeholder="選擇要取消的盯盤項目...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_id = self.values[0]
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM market_alerts WHERE id = ? AND user_id = ?",
                (selected_id, str(interaction.user.id)),
            )
            conn.commit()
            conn.close()
            await interaction.response.send_message(
                f"✅ 成功取消並刪除編號 `{selected_id}` 的盯盤任務！", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 取消失敗：{e}", ephemeral=True
            )


class ManageAlertsView(discord.ui.View):

    def __init__(self, alerts):
        super().__init__(timeout=60)
        self.add_item(CancelAlertSelect(alerts))


# ===================== 常駐面板的 View =====================
class MarketPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔍 深度查詢道具",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_market_search_btn_v2",
    )
    async def search_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # 💡 點擊後從資料庫撈取最新熱門/出現過的道具名稱（最多25個）
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT item_name FROM market_prices ORDER BY id DESC LIMIT 25"
            )
            popular_items = [row[0] for row in cursor.fetchall()]
            conn.close()
        except Exception:
            popular_items = []

        view = MarketSearchSelectView(popular_items)
        await interaction.response.send_message(
            "🔍 **請選擇熱門道具快速查詢，或點擊下方按鈕手動輸入關鍵字：**",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="🔔 設定價格盯盤",
        style=discord.ButtonStyle.success,
        custom_id="persistent_market_alert_btn_v2",
    )
    async def alert_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(MarketAlertModal())

    @discord.ui.button(
        label="📋 管理我的盯盤",
        style=discord.ButtonStyle.secondary,
        custom_id="persistent_market_manage_btn_v2",
    )
    async def manage_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                    SELECT id, item_keyword, target_price, alert_type 
                    FROM market_alerts 
                    WHERE user_id = ? AND is_active = 1
                """,
                (str(interaction.user.id),),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        if not rows:
            await interaction.response.send_message(
                "📭 你目前沒有設定任何進行中的價格盯盤任務。", ephemeral=True
            )
            return

        view = ManageAlertsView(rows)
        await interaction.response.send_message(
            "📋 **以下是你當前所有的盯盤任務，選擇下方選單即可刪除/取消：**",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="📊 資料庫狀態",
        style=discord.ButtonStyle.grey,
        custom_id="persistent_market_status_btn_v2",
    )
    async def status_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), MAX(timestamp) FROM market_prices")
            count, last_time = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM market_alerts WHERE is_active = 1")
            active_alerts = cursor.fetchone()[0]
            conn.close()
        except Exception:
            count, last_time, active_alerts = 0, "未知", 0

        embed = discord.Embed(
            title="⚙️ 靈谷市場資料庫即時狀態",
            description=(
                f"• 市場數據總筆數：`{count:,}` 筆\n• 進行中盯盤任務："
                f" `{active_alerts}` 個\n• 最後同步時間："
                f" `{last_time if last_time else '尚無資料'}`\n• 同步頻率：每 **10"
                " 分鐘** 自動抓取全域快照"
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="🔄 強制同步資料",
        style=discord.ButtonStyle.danger,
        custom_id="persistent_market_sync_btn_v2",
        row=1,
    )
    async def sync_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 只有管理員可以手動強制同步資料！", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        success, result = await execute_market_sync(interaction.client)
        if success:
            await interaction.followup.send(
                f"✅ 手動同步成功！本次共寫入 `{result}` 筆市場資料。", ephemeral=True
            )
        else:
            await interaction.followup.send(f"❌ 同步失敗：{result}", ephemeral=True)


# ===================== 主 Cog (背景同步 + 盯盤檢查器) =====================
class ValeMarketSync(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.sync_market_data.start()

    def cog_unload(self):
        self.sync_market_data.cancel()

    @tasks.loop(minutes=10)
    async def sync_market_data(self):
        await execute_market_sync(self.bot)

    @sync_market_data.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()
        print("🚀 機器人已就緒，正在執行【首次開機即時同步】...")
        await execute_market_sync(self.bot)

    @app_commands.command(
        name="架設市場面板",
        description="在當前頻道架設一個常駐的靈谷全球市場查詢卡片 (PRO版+盯盤)",
    )
    async def setup_market_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 只有伺服器管理員才能架設市場面板！", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📊 靈谷全球市場情報站 (ValeMarket PRO)",
            description=(
                "歡迎使用公會專屬頂級市場經濟系統！\n\n• 🔄 每 **10 分鐘**"
                " 自動同步全球市場最新快照。\n• 🔍 **深度查詢**：支援熱門下拉選單快選與關鍵字搜尋。\n•"
                " 🔔 **價格盯盤**：設定目標價，達成時機器人**自動私訊通知一次**。\n• 📋"
                " **清單管理**：隨時查看或自主取消進行中的盯盤任務。\n\n👉 **請點擊下方按鈕開始使用！**"
            ),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="小貓咪智能公會系統 • 智慧經濟引擎")

        view = MarketPanelView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            "✅ 成功在當前頻道架設【PRO全功能版】市場查詢常駐面板！", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ValeMarketSync(bot))
