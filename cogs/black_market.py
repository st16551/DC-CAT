import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from utils import get_wallet_balance, modify_balance

# 假設這是你的黑市詛咒道具清單
BLACK_MARKET_ITEMS = {
    "debuff_reverse": {"name": "發言倒裝句咒語", "price": 1000, "hours": 24, "type": "reverse"},
    "debuff_mosaic": {"name": "打碼馬賽克眼鏡", "price": 1500, "hours": 12, "type": "mosaic"},
}

# 儲存全域活躍詛咒的字典（或從外部匯入）
active_debuffs = {}

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
        user_id = str(interaction.user.id)

        # 1. 再次在提交時檢查錢包餘額（雙重保險）
        current_coins = get_wallet_balance(user_id)
        if current_coins < self.cost:
            await interaction.followup.send(f"❌ 你的 SU 幣不足！購買【{self.item_name}】需要 `{self.cost} SU幣`，你目前只有 `{current_coins} SU幣`。", ephemeral=True)
            return

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

        if target_member.id == interaction.user.id:
            await interaction.followup.send("❌ 不能對自己施展詛咒！", ephemeral=True)
            return

        # 2. 執行安全扣款
        success = modify_balance(user_id, -self.cost, tx_type=f"buy_{self.debuff_type}", sender_id="BLACK_MARKET")
        if not success:
            await interaction.followup.send("❌ 扣款失敗，請稍後再試或聯繫管理員。", ephemeral=True)
            return

        # 3. 記錄詛咒狀態
        key = f"{guild.id}_{target_member.id}"
        active_debuffs[key] = {
            "guild_id": guild.id,
            "user_id": target_member.id,
            "type": self.debuff_type,
            "expire_at": datetime.now() + timedelta(hours=self.hours),
        }

        await interaction.followup.send(
            f"🎯 施法成功！已對 **{target_member.display_name}** 施加【{self.item_name}】，持續 {self.hours} 小時！已扣除 `{self.cost} SU幣`。",
            ephemeral=True,
        )
        
        if guild.system_channel:
            await guild.system_channel.send(
                f"🔮 **【黑市詛咒】** {interaction.user.mention} 成功對 **{target_member.display_name}** 施展了 **{self.item_name}**！"
            )

class BlackMarketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=item["name"], 
                description=f"售價: {item['price']} SU幣 | 持續 {item['hours']} 小時", 
                value=key
            )
            for key, item in BLACK_MARKET_ITEMS.items()
        ]
        super().__init__(placeholder="點此選購黑市整人道具...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_key = self.values[0]
        item = BLACK_MARKET_ITEMS[item_key]
        user_id = str(interaction.user.id)

        # 點擊選單時先檢查餘額，若錢不夠直接阻止並跳出 Modal
        current_coins = get_wallet_balance(user_id)
        if current_coins < item["price"]:
            await interaction.response.send_message(
                f"❌ 你的 SU 幣不足！【{item['name']}】售價為 `{item['price']} SU幣`，你目前只有 `{current_coins} SU幣`。", 
                ephemeral=True
            )
            return

        # 錢夠的話，跳出輸入受害者的 Modal
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

    @app_commands.command(name="黑市", description="開啟地下黑市，購買整人與詛咒道具")
    async def black_market(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏴‍☠️ 地下黑市道具坊",
            description="歡迎來到見不得光的黑市！這裡的道具可以對其他人施加惡整詛咒。\n購買時將直接從你的 **SU 幣錢包** 中扣款，請謹慎使用！",
            color=0x2b2d31
        )
        embed.add_field(
            name="目前黑市商品", 
            value="• **發言倒裝句咒語** (1,000 SU幣 / 24小時)\n• **打碼馬賽克眼鏡** (1,500 SU幣 / 12小時)", 
            inline=False
        )
        view = BlackMarketView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BlackMarketCog(bot))
