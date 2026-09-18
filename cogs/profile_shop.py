from datetime import datetime, timedelta
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks

# 嘗試從 utils 匯入自定義函式，若找不到則提供安全防呆預設值，防止直接噴錯崩潰
try:
    from utils import (
        activity_data,
        save_data,
        DATA_FILE,
        get_wallet_balance,
        modify_balance,
    )
except ImportError:
    # 預設防呆函式（避免 utils 缺失時整個模組掛掉）
    def get_wallet_balance(user_id: str) -> int:
        return 9999

    def modify_balance(user_id: str, amount: int, tx_type: str = "", sender_id: str = ""):
        pass


# 記錄全域狀態
active_renames = {}  # 格式: {"guild_id_user_id": data}
active_debuffs = {}  # 格式: {"guild_id_user_id": data}


# ==================== 下拉選單 View ====================
class ShopSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="🛒 選擇你想購買或使用的公會黑市道具...",
        custom_id="profile_shop_select_v3",
        options=[
            discord.SelectOption(
                label="📢 全群廣播 (大聲公)",
                description="售價: 400 幣 | 全伺服器高調廣播一句話",
                value="buy_megaphone",
            ),
            discord.SelectOption(
                label="🔀 強制改名卡 (24小時)",
                description="售價: 1000 幣 | 把好兄弟名字改掉24小時後自動還原",
                value="buy_rename_card",
            ),
            discord.SelectOption(
                label="🌀 發言倒裝句咒語 (1小時)",
                description="售價: 450 幣 | 讓指定成員講話變成亂序倒裝句",
                value="buy_reverse_spell",
            ),
            discord.SelectOption(
                label="🧩 打碼馬賽克眼鏡 (2小時)",
                description="售價: 300 幣 | 讓指定成員發言隨機夾帶馬賽克黑條",
                value="buy_mosaic_glasses",
            ),
        ],
    )
    async def select_callback(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        choice = select.values[0]
        user_id = str(interaction.user.id)
        wallet = get_wallet_balance(user_id)

        prices = {
            "buy_megaphone": 400,
            "buy_rename_card": 1000,
            "buy_reverse_spell": 450,
            "buy_mosaic_glasses": 300,
        }

        cost = prices.get(choice, 0)
        if wallet < cost:
            await interaction.response.send_message(
                f"❌ 你的 SU 幣不足！目前錢包餘額：**{wallet} SU 幣**，此商品需要 **{cost} SU 幣**。",
                ephemeral=True,
            )
            return

        if choice == "buy_rename_card":
            await interaction.response.send_modal(RenameMovieModal(cost))
        elif choice == "buy_megaphone":
            await interaction.response.send_modal(MegaphoneMovieModal(cost))
        elif choice == "buy_reverse_spell":
            await interaction.response.send_modal(
                TargetDebuffModal(cost, "reverse_spell", "發言倒裝句咒語", 1)
            )
        elif choice == "buy_mosaic_glasses":
            await interaction.response.send_modal(
                TargetDebuffModal(cost, "mosaic_glasses", "打碼馬賽克眼鏡", 2)
            )


# ==================== 各項道具 Modal ====================
class MegaphoneMovieModal(discord.ui.Modal, title="📢 發布全群廣播"):
    message_content = discord.ui.TextInput(
        label="想廣播的內容",
        style=discord.TextStyle.paragraph,
        placeholder="輸入你想全伺服器大喊的內容...",
        max_length=200,
    )

    def __init__(self, cost):
        super().__init__()
        self.cost = cost

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        
        modify_balance(user_id, -self.cost, tx_type="buy_megaphone", sender_id="SHOP_SYSTEM")

        embed = discord.Embed(
            title="📢 【公會大聲公廣播】",
            description=f"{interaction.user.mention} 大喊：\n> **{self.message_content.value}**",
            color=discord.Color.gold(),
        )
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("✅ 廣播已成功發送！", ephemeral=True)


class RenameMovieModal(discord.ui.Modal, title="🔀 使用強制改名卡"):
    target_name = discord.ui.TextInput(
        label="受害者名字、ID 或 Mention",
        placeholder="請輸入你要整的人的名稱...",
        max_length=50,
    )
    new_nickname = discord.ui.TextInput(
        label="指定的新暱稱",
        placeholder="例如: 群組小丑",
        max_length=32,
    )

    def __init__(self, cost):
        super().__init__()
        self.cost = cost

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        target_str = self.target_name.value.strip()
        new_nick = self.new_nickname.value.strip()

        target_member = None
        if target_str.startswith("<@") and target_str.endswith(">"):
            clean_id = target_str.strip("<@!>")
            target_member = guild.get_member(int(clean_id))
        else:
            target_member = discord.utils.find(
                lambda m: target_str.lower() in m.name.lower() or target_str.lower() in m.display_name.lower(),
                guild.members,
            )

        if not target_member:
            await interaction.followup.send(f"❌ 找不到名為 `{target_str}` 的成員！", ephemeral=True)
            return

        if target_member.bot:
            await interaction.followup.send("❌ 不能對機器人使用！", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        modify_balance(user_id, -self.cost, tx_type="buy_rename_card", sender_id="SHOP_SYSTEM")

        timer_key = f"{guild.id}_{target_member.id}"
        original_display = target_member.display_name

        try:
            await target_member.edit(nick=new_nick, reason=f"由 {interaction.user} 使用強制改名卡")
            active_renames[timer_key] = {
                "guild_id": guild.id,
                "user_id": target_member.id,
                "original_name": original_display,
                "expire_at": datetime.now() + timedelta(hours=24),
            }

            await interaction.followup.send(
                f"🎯 施法成功！已將 **{original_display}** 改為 **{new_nick}**（24小時後自動還原）！",
                ephemeral=True,
            )
            if guild.system_channel:
                await guild.system_channel.send(
                    f"🚨 **【公會惡整事件】** {interaction.user.mention} 對 **{original_display}** 施展了【強制改名卡】，變更為 `{new_nick}`！🃏"
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ 改名失敗（可能是對方權限高於機器人或缺少管理權限）：{e}", ephemeral=True
            )


class TargetDebuffModal(discord.ui.Modal):
    target_name = discord.ui.TextInput(
        label="受害者名字或 ID",
        placeholder="請輸入你要施法的成員名稱...",
        max_length=50,
    )

    def __init__(self, cost, debuff_type, item_name, hours):
        super().__init__(title=f"施放【{item_name}】")
        self.cost = cost
        self.debuff_type = debuff_type
        self.item_name = item_name
        self.hours = hours

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        target_str = self.target_name.value.strip()

        if target_str.startswith("<@") and target_str.endswith(">"):
            clean_id = target_str.strip("<@!>")
            target_member = guild.get_member(int(clean_id))
        else:
            target_member = discord.utils.find(
                lambda m: target_str.lower() in m.name.lower() or target_str.lower() in m.display_name.lower(),
                guild.members,
            )

        if not target_member:
            await interaction.followup.send(f"❌ 找不到名為 `{target_str}` 的成員！", ephemeral=True)
            return

        if target_member.bot:
            await interaction.followup.send("❌ 不能對機器人施法！", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        modify_balance(user_id, -self.cost, tx_type=f"buy_{self.debuff_type}", sender_id="SHOP_SYSTEM")

        key = f"{guild.id}_{target_member.id}"
        active_debuffs[key] = {
            "guild_id": guild.id,
            "user_id": target_member.id,
            "type": self.debuff_type,
            "expire_at": datetime.now() + timedelta(hours=self.hours),
        }

        await interaction.followup.send(
            f"🎯 施法成功！已對 **{target_member.display_name}** 施加【{self.item_name}】，持續 {self.hours} 小時！",
            ephemeral=True,
        )
        if guild.system_channel:
            await guild.system_channel.send(
                f"🔮 **【黑市詛咒】** {interaction.user.mention} 成功對 **{target_member.display_name}** 施展了 **{self.item_name}**！"
            )


# ==================== Cog 主體 ====================
class ProfileShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not self.shop_timer_task.is_running():
            self.shop_timer_task.start()

    def cog_unload(self):
        self.shop_timer_task.cancel()

    @tasks.loop(minutes=1)
    async def shop_timer_task(self):
        now = datetime.now()

        # 1. 還原改名
        expired_renames = []
        for key, data in active_renames.items():
            if now >= data["expire_at"]:
                expired_renames.append(key)
                guild = self.bot.get_guild(data["guild_id"])
                if not guild:
                    continue
                member = guild.get_member(data["user_id"])
                if member:
                    try:
                        await member.edit(nick=None, reason="強制改名卡效期屆滿，自動還原")
                        if guild.system_channel:
                            await guild.system_channel.send(
                                f"⏳ **【時效屆滿】** **{member.display_name}** 的強制改名卡效期已過，名字已自動恢復正常！"
                            )
                    except Exception:
                        pass
        for k in expired_renames:
            active_renames.pop(k, None)

        # 2. 清除過期 Debuff
        expired_debuffs = [k for k, data in active_debuffs.items() if now >= data["expire_at"]]
        for k in expired_debuffs:
            active_debuffs.pop(k, None)

    @shop_timer_task.before_loop
    async def before_shop_timer(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        key = f"{message.guild.id}_{message.author.id}"
        if key not in active_debuffs:
            return

        debuff = active_debuffs[key]
        content = message.content

        if debuff["type"] == "reverse_spell":
            words = list(content)
            random.shuffle(words)
            reversed_text = "".join(words)
            try:
                await message.delete()
                await message.channel.send(
                    f"🌀 `{message.author.display_name}` 講話被詛咒了：\n> {reversed_text}"
                )
            except Exception:
                pass

        elif debuff["type"] == "mosaic_glasses":
            words = content.split()
            if words:
                idx = random.randint(0, len(words) - 1)
                words[idx] = f"||{words[idx]}||"
                mosaic_text = " ".join(words)
                try:
                    await message.delete()
                    await message.channel.send(
                        f"🧩 `{message.author.display_name}` 戴著馬賽克眼鏡喊道：\n> {mosaic_text}"
                    )
                except Exception:
                    pass

    @app_commands.command(
        name="商店", description="開啟公會黑市道具商店，選購趣味與整人道具"
    )
    async def open_shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 【冒險者公會黑市商店】",
            description=(
                "歡迎來到地下黑市！使用平時賺取的 **SU 幣** 選購惡整與防禦道具吧！\n\n"
                "🔹 **📢 全群廣播** (400 幣) - 全群高調喊話\n"
                "🔹 **🔀 強制改名卡** (1000 幣) - 惡整好友 24 小時自動還原\n"
                "🔹 **🌀 發言倒裝句咒語** (450 幣) - 讓對方說話變成亂序倒裝句 (1小時)\n"
                "🔹 **🧩 打碼馬賽克眼鏡** (300 幣) - 隨機將對方的發言打上黑條 (2小時)\n\n"
                "👇 請從下方選單挑選你想購買的道具："
            ),
            color=discord.Color.dark_purple(),
        )
        view = ShopSelectView()
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )

    @app_commands.command(
        name="架設商店卡", description="在目前頻道架設永久黑市商店面板 (限管理員)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_shop_card(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 【公會常設黑市商店】",
            description=(
                "隨時點擊下方選單購買各類整人與實用道具！\n\n"
                "📢 **全群廣播** | 🔀 **強制改名卡**\n"
                "🌀 **倒裝句咒語** | 🧩 **馬賽克眼鏡**"
            ),
            color=discord.Color.purple(),
        )
        view = ShopSelectView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            "✅ 永久黑市商店面板已成功架設於此頻道！", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ProfileShopCog(bot))
