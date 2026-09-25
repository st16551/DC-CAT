import random
import re
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from utils import get_wallet_balance, modify_balance, get_db_connection

# 已經根據平衡性調整過價格與時效的黑市道具清單
BLACK_MARKET_ITEMS = {
    "broadcast": {
        "name": "全群廣播 / 大聲公",
        "price": 350,
        "hours": 0,  # 立即性消耗道具，無持續時間
        "type": "broadcast",
        "description": "向當前頻道廣播你的重要訊息"
    },
    "rename_card": {
        "name": "強制改名卡",
        "price": 550,
        "hours": 24,  # 持續 24 小時自動還原
        "type": "rename",
        "description": "強制更改受害者名字 24 小時"
    },
    "debuff_reverse": {
        "name": "發言倒裝句咒語",
        "price": 450,
        "hours": 1,
        "type": "reverse",
        "description": "讓目標 1 小時內發言變成倒裝句"
    },
    "debuff_mosaic": {
        "name": "打碼馬賽克眼鏡",
        "price": 300,
        "hours": 2,
        "type": "mosaic",
        "description": "讓目標 2 小時內發言隨機被馬賽克"
    },
}

class TargetDebuffModal(discord.ui.Modal):
    def __init__(self, cost, debuff_type, item_name, hours):
        super().__init__(title=f"施放【{item_name}】")
        
        self.cost = cost
        self.debuff_type = debuff_type
        self.item_name = item_name
        self.hours = hours

        if debuff_type == "broadcast":
            self.target_name = discord.ui.TextInput(
                label="廣播內容訊息",
                placeholder="請輸入你想廣播公告的內容...",
                style=discord.TextStyle.paragraph,
                max_length=300,
            )
            self.add_item(self.target_name)
        else:
            self.target_name = discord.ui.TextInput(
                label="受害者名字、ID 或 @標註",
                placeholder="例如: 小明 或 123456789 或 @小明",
                max_length=50,
            )
            self.add_item(self.target_name)

            if debuff_type == "rename":
                self.new_nickname = discord.ui.TextInput(
                    label="強制改為的新名稱",
                    placeholder="請輸入想惡整他的新暱稱...",
                    max_length=32,
                )
                self.add_item(self.new_nickname)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        # 1. 再次檢查錢包餘額
        current_coins = get_wallet_balance(user_id)
        if current_coins < self.cost:
            await interaction.followup.send(f"❌ 你的 SU 幣不足！購買【{self.item_name}】需要 `{self.cost} SU幣`，你目前只有 `{current_coins} SU幣`。", ephemeral=True)
            return

        guild = interaction.guild

        # 處理「全群廣播」的特殊邏輯
        if self.debuff_type == "broadcast":
            broadcast_content = self.target_name.value.strip()

            success = modify_balance(user_id, -self.cost, tx_type="buy_broadcast", sender_id="BLACK_MARKET")
            if not success:
                await interaction.followup.send("❌ 扣款失敗，請稍後再試或聯繫管理員。", ephemeral=True)
                return

            await interaction.followup.send(f"📢 廣播成功！已消耗 `{self.cost} SU幣` 發送大聲公。", ephemeral=True)

            target_channel = interaction.channel
            if target_channel:
                await target_channel.send(
                    f"📢 **【黑市大聲公】**\n"
                    f"來自 {interaction.user.mention} 的重金宣告：\n> {broadcast_content}"
                )
            return

        # 解析並尋找目標成員
        target_str = self.target_name.value.strip()
        target_member = None

        if target_str.startswith("<@") and target_str.endswith(">"):
            clean_id = target_str.strip("<@!>")
            if clean_id.isdigit():
                target_member = guild.get_member(int(clean_id))
                if not target_member:
                    try:
                        target_member = await guild.fetch_member(int(clean_id))
                    except Exception:
                        pass
        elif target_str.isdigit():
            target_member = guild.get_member(int(target_str))
            if not target_member:
                try:
                    target_member = await guild.fetch_member(int(target_str))
                except Exception:
                    pass

        if not target_member:
            for m in guild.members:
                if (target_str.lower() in m.name.lower() or 
                    target_str.lower() in m.display_name.lower() or 
                    (m.global_name and target_str.lower() in m.global_name.lower())):
                    target_member = m
                    break

        if not target_member:
            await interaction.followup.send(f"❌ 找不到名為或代號為 `{target_str}` 的成員！請確認對方在伺服器內。", ephemeral=True)
            return

        if target_member.bot:
            await interaction.followup.send("❌ 不能對機器人施法！", ephemeral=True)
            return

        if target_member.id == interaction.user.id and self.debuff_type != "rename":
            await interaction.followup.send("❌ 不能對自己施展詛咒！", ephemeral=True)
            return

        # 2. 執行安全扣款
        success = modify_balance(user_id, -self.cost, tx_type=f"buy_{self.debuff_type}", sender_id="BLACK_MARKET")
        if not success:
            await interaction.followup.send("❌ 扣款失敗，請稍後再試或聯繫管理員。", ephemeral=True)
            return

        old_nick = target_member.display_name

        # 如果是強制改名卡
        if self.debuff_type == "rename":
            new_nick = self.new_nickname.value.strip()
            try:
                await target_member.edit(nick=new_nick, reason=f"黑市強制改名卡由 {interaction.user} 購買施放")
            except discord.Forbidden:
                await interaction.followup.send("❌ 機器人權限不足或身分組低於對方，無法改名！已全額退款。", ephemeral=True)
                modify_balance(user_id, self.cost, tx_type="refund_rename_fail", sender_id="BLACK_MARKET")
                return
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ 改名失敗 ({e})！已全額退款。", ephemeral=True)
                modify_balance(user_id, self.cost, tx_type="refund_rename_fail", sender_id="BLACK_MARKET")
                return

        # 3. 記錄詛咒狀態到 SQLite 資料庫中
        key = f"{guild.id}_{target_member.id}"
        expire_at_str = (datetime.now() + timedelta(hours=self.hours)).isoformat()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO active_debuffs (id, guild_id, user_id, type, old_nickname, expire_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key, guild.id, target_member.id, self.debuff_type, old_nick, expire_at_str))
        conn.commit()
        conn.close()

        if self.debuff_type == "rename":
            await interaction.followup.send(
                f"🎯 施法成功！已將 **{old_nick}** 強制改名為 **{new_nick}**，持續 {self.hours} 小時！已扣除 `{self.cost} SU幣`。",
                ephemeral=True,
            )
            if interaction.channel:
                await interaction.channel.send(f"🔀 **【黑市整人】** {interaction.user.mention} 對 **{old_nick}** 使用了 **強制改名卡**！")
            return

        await interaction.followup.send(
            f"🎯 施法成功！已對 **{target_member.display_name}** 施加【{self.item_name}】，持續 {self.hours} 小時！已扣除 `{self.cost} SU幣`。",
            ephemeral=True,
        )
        
        if interaction.channel:
            await interaction.channel.send(f"🔮 **【黑市詛咒】** {interaction.user.mention} 成功對 **{target_member.display_name}** 施展了 **{self.item_name}**！")

class BlackMarketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=item["name"], 
                description=f"售價: {item['price']} SU幣 | {item['description']}", 
                value=key
            )
            for key, item in BLACK_MARKET_ITEMS.items()
        ]
        super().__init__(placeholder="點此選購黑市整人道具...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_key = self.values[0]
        item = BLACK_MARKET_ITEMS[item_key]
        user_id = str(interaction.user.id)

        current_coins = get_wallet_balance(user_id)
        if current_coins < item["price"]:
            await interaction.response.send_message(
                f"❌ 你的 SU 幣不足！【{item['name']}】售價為 `{item['price']} SU幣`，你目前只有 `{current_coins} SU幣`。", 
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            TargetDebuffModal(
                cost=item["price"], 
                debuff_type=item["type"], 
                item_name=item["name"], 
                hours=item["hours"]
            )
        )

class BlackMarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(BlackMarketSelect())

class BlackMarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_cache = {}
        self.check_debuffs_task.start()

    def cog_unload(self):
        self.check_debuffs_task.cancel()

    async def get_or_create_webhook(self, channel):
        if channel.id in self.webhook_cache:
            webhook = self.webhook_cache[channel.id]
            try:
                if webhook and webhook.channel.id == channel.id:
                    return webhook
            except Exception:
                pass
        try:
            webhooks = await channel.webhooks()
            webhook = discord.utils.get(webhooks, name="BlackMarketProxy")
            if not webhook:
                webhook = await channel.create_webhook(name="BlackMarketProxy")
            self.webhook_cache[channel.id] = webhook
            return webhook
        except Exception:
            return None

    # 背景任務：每分鐘檢查過期狀態並自動還原
    @tasks.loop(minutes=1)
    async def check_debuffs_task(self):
        now = datetime.now()
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, guild_id, user_id, type, old_nickname, expire_at FROM active_debuffs")
        rows = cursor.fetchall()
        expired_ids = []

        for row in rows:
            record_id = row["id"]
            guild_id = row["guild_id"]
            user_id = row["user_id"]
            debuff_type = row["type"]
            old_nickname = row["old_nickname"]
            expire_at = datetime.fromisoformat(row["expire_at"])

            if now >= expire_at:
                expired_ids.append(record_id)
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                member = guild.get_member(user_id)
                if not member:
                    try:
                        member = await guild.fetch_member(user_id)
                    except Exception:
                        continue

                if debuff_type == "rename" and member:
                    try:
                        await member.edit(nick=old_nickname, reason="黑市強制改名時間到期，自動還原")
                        if guild.system_channel:
                            await guild.system_channel.send(f"⏳ **【黑市自動還原】** **{old_nickname}** 的強制改名時間已到，已自動恢復原名！")
                    except Exception:
                        pass
                else:
                    if guild.system_channel and member:
                        await guild.system_channel.send(f"⏳ **【黑市解除】** **{member.display_name}** 身上的黑市詛咒已自然解除。")

        if expired_ids:
            cursor.executemany("DELETE FROM active_debuffs WHERE id = ?", [(rid,) for rid in expired_ids])
            conn.commit()

        conn.close()

    @check_debuffs_task.before_loop
    async def before_check_debuffs(self):
        await self.bot.wait_until_ready()

    # 監聽被施加詛咒者的發言（倒裝句、馬賽克）
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT type, expire_at FROM active_debuffs WHERE guild_id = ? AND user_id = ?", (message.guild.id, message.author.id))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return

        debuff_type = row["type"]
        expire_at = datetime.fromisoformat(row["expire_at"])

        if datetime.now() >= expire_at:
            return  # 時間到了由背景任務清理

        if debuff_type not in ["reverse", "mosaic"]:
            return

        content = message.content
        if not content:
            return

        # 處理詛咒轉換效果
        if debuff_type == "reverse":
            # 倒裝句處理
            content = content[::-1]
        elif debuff_type == "mosaic":
            # 隨機馬賽克處理
            chars = list(content)
            for i in range(len(chars)):
                if chars[i].strip() and random.random() < 0.4:
                    chars[i] = "█"
            content = "".join(chars)

        try:
            await message.delete()
        except Exception:
            return

        webhook = await self.get_or_create_webhook(message.channel)
        if not webhook:
            return

        avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
        display_name = message.author.display_name

        try:
            await webhook.send(
                content=content,
                username=display_name,
                avatar_url=avatar_url,
            )
        except Exception:
            pass

    @app_commands.command(name="黑市", description="開啟地下黑市，購買整人與詛咒道具")
    async def black_market(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏴‍☠️ 地下黑市道具坊",
            description="歡迎來到見不得光的黑市！這裡的道具可以對其他人施加惡整詛咒或發布廣播。\n購買時將直接從你的 **SU 幣錢包** 中扣款，請謹慎使用！",
            color=0x2b2d31
        )
        embed.add_field(
            name="目前黑市商品", 
            value=(
                "• **📢 全群廣播 / 大聲公** (350 SU幣 / 立即生效)\n"
                "• **🔀 強制改名卡** (550 SU幣 / 24小時自動還原)\n"
                "• **🔀 發言倒裝句咒語** (450 SU幣 / 1小時)\n"
                "• **🧩 打碼馬賽克眼鏡** (300 SU幣 / 2小時)"
            ), 
            inline=False
        )
        view = BlackMarketView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="我的黑市狀態", description="查看你自己目前身上是否有黑市詛咒或強制改名與剩餘時間")
    async def my_black_market_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT type, old_nickname, expire_at FROM active_debuffs WHERE guild_id = ? AND user_id = ?", (guild.id, user.id))
        row = cursor.fetchone()
        conn.close()

        if not row:
            await interaction.response.send_message("✨ 你目前非常乾淨，身上沒有任何黑市詛咒或強制改名狀態！", ephemeral=True)
            return

        debuff_type = row["type"]
        expire_at = datetime.fromisoformat(row["expire_at"])
        
        type_names = {
            "rename": "🔀 強制改名卡",
            "reverse": "🔀 發言倒裝句咒語",
            "mosaic": "🧩 打碼馬賽克眼鏡"
        }

        now = datetime.now()
        remaining = expire_at - now
        total_seconds = int(remaining.total_seconds())

        if total_seconds > 0:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            time_str = f"**{hours} 小時 {minutes} 分鐘**"
        else:
            time_str = "即將解除"

        item_desc = type_names.get(debuff_type, debuff_type)

        embed = discord.Embed(
            title="🔍 你的黑市狀態查詢",
            description=f"你目前正在承受以下黑市效果：",
            color=0xffaa00
        )
        embed.add_field(
            name=f"道具類型：{item_desc}",
            value=f"• 剩餘時效：{time_str}\n• 到期時間點：{expire_at.strftime('%Y-%m-%d %H:%M:%S')}",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BlackMarketCog(bot))
