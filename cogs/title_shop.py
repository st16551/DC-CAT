import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from utils import activity_data, save_data, DATA_FILE, get_wallet_balance, modify_balance

SHOP_ITEMS_PART1 = {
    "item_1": {"name": "薯條加大", "price": 500, "color": 0xFFA726},
    "item_2": {"name": "帶薪拉屎", "price": 500, "color": 0x78909C},
    "item_3": {"name": "活化石預備軍", "price": 500, "color": 0x8D6E63},
    "item_4": {"name": "邏輯死絕", "price": 500, "color": 0xFFCA28},
    "item_5": {"name": "隊友祭天", "price": 500, "color": 0xEF5350},
    "item_6": {"name": "摸魚大師", "price": 500, "color": 0x26C6DA},
    "item_7": {"name": "躺平廢物", "price": 500, "color": 0xB39DDB},
    "item_8": {"name": "已讀不回", "price": 500, "color": 0x90A4AE},
    "item_9": {"name": "減肥明天再說", "price": 500, "color": 0xEC407A},
    "item_10": {"name": "全自動句點王", "price": 500, "color": 0x7E57C2},
    "item_11": {"name": "修仙猝死中", "price": 1500, "color": 0x4DD0E1},
    "item_12": {"name": "專坑親友", "price": 1500, "color": 0xFFEE58},
    "item_13": {"name": "加班到見祖宗", "price": 1500, "color": 0xAB47BC},
    "item_14": {"name": "落地直接成盒", "price": 1500, "color": 0xFF5252},
    "item_15": {"name": "鐵頭撞南牆", "price": 1500, "color": 0x8D6E63},
}

SHOP_ITEMS_PART2 = {
    "item_16": {"name": "今天想放生誰", "price": 1500, "color": 0xEC407A},
    "item_17": {"name": "非洲酋長本尊", "price": 1500, "color": 0x795548},
    "item_18": {"name": "上線只為發呆", "price": 1500, "color": 0x80DEEA},
    "item_19": {"name": "不服上來單挑", "price": 1500, "color": 0xFF7043},
    "item_20": {"name": "牌爛靠賽", "price": 1500, "color": 0x66BB6A},
    "item_21": {"name": "精神病院VIP", "price": 4000, "color": 0xFF4081},
    "item_22": {"name": "原地直接炸開", "price": 4000, "color": 0xFFD700},
    "item_23": {"name": "吃土總裁", "price": 4000, "color": 0x00E676},
    "item_24": {"name": "公會金主爸爸", "price": 4000, "color": 0xFFD700},
    "item_25": {"name": "走路容易被雷劈", "price": 4000, "color": 0x00B0FF},
    "item_26": {"name": "厚顏無恥之徒", "price": 4000, "color": 0x78909C},
    "item_27": {"name": "智商稅大戶", "price": 4000, "color": 0xE040FB},
    "item_28": {"name": "活生生的笑話", "price": 4000, "color": 0xFF6D00},
    "item_29": {"name": "講話冷到結冰", "price": 4000, "color": 0x80FFFF},
    "item_30": {"name": "已在地府登記", "price": 4000, "color": 0x37474F},
}

async def assign_shop_role(member: discord.Member, title_name: str, color_hex: int):
    """專門幫商店稱號建立身分組與派發的輔助函式"""
    guild = member.guild
    
    # 移除其他商城稱號身分組（可依需求保留或互斥，這裡示範自動建立與賦予）
    role = discord.utils.get(guild.roles, name=title_name)
    if not role:
        try:
            role = await guild.create_role(name=title_name, color=discord.Color(color_hex), reason="公會商店稱號身分組")
        except discord.Forbidden:
            pass
    if role and role not in member.roles:
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            pass

async def handle_shop_purchase(interaction: discord.Interaction, item_key: str, item_dict: dict):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)
    
    if guild_id not in activity_data:
        activity_data[guild_id] = {}
    if user_id not in activity_data[guild_id]:
        activity_data[guild_id][user_id] = {
            "text_count": 0, "voice_time": 0, 
            "level": 1, "exp": 0, "titles": {}, "current_title": "新手冒險者"
        }
    
    user_data = activity_data[guild_id][user_id]
    item = item_dict[item_key]
    price = item["price"]
    title_name = item["name"]

    if "titles" not in user_data or isinstance(user_data["titles"], list):
        user_data["titles"] = {}

    # 從 SQLite 查詢目前實際餘額
    current_coins = get_wallet_balance(user_id)
    if current_coins < price:
        await interaction.followup.send(f"你的 SU 幣不足！還差 `{price - current_coins} SU幣`。", ephemeral=True)
        return

    now = datetime.now()
    if title_name in user_data["titles"]:
        try:
            current_expiry = datetime.fromisoformat(user_data["titles"][title_name])
            base_time = max(current_expiry, now)
        except Exception:
            base_time = now
        new_expiry = base_time + timedelta(days=30)
        action_text = "續約成功！有效期限已延長 30 天"
    else:
        new_expiry = now + timedelta(days=30)
        action_text = "成功購買！獲得 30 天使用權"

    # 透過 SQLite 安全扣款（交易類型為 shop_buy）
    success = modify_balance(user_id, -price, tx_type="shop_buy", sender_id="SHOP")
    if not success:
        await interaction.followup.send("扣款失敗，請稍後再試或聯繫管理員。", ephemeral=True)
        return

    user_data["titles"][title_name] = new_expiry.isoformat()
    user_data["current_title"] = title_name
    save_data(DATA_FILE, activity_data)

    await assign_shop_role(interaction.user, title_name, item["color"])
    await interaction.followup.send(f"恭喜 **{title_name}** {action_text}！已自動從 SQLite 錢包扣除 `{price} SU幣`。", ephemeral=True)

class ShopSelect1(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=item["name"], description=f"售價: {item['price']} SU幣 (30天)", value=key)
            for key, item in SHOP_ITEMS_PART1.items()
        ]
        super().__init__(placeholder="點此選購：日常幹話與社畜系列...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await handle_shop_purchase(interaction, self.values[0], SHOP_ITEMS_PART1)

class ShopSelect2(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=item["name"], description=f"售價: {item['price']} SU幣 (30天)", value=key)
            for key, item in SHOP_ITEMS_PART2.items()
        ]
        super().__init__(placeholder="點此選購：大老整活與瘋狂系列...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await handle_shop_purchase(interaction, self.values[0], SHOP_ITEMS_PART2)

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect1())
        self.add_item(ShopSelect2())

class ProfileShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="個人檔案", description="查看你的等級、稱號、經驗值與 SU幣資產")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(target.id)
        user = activity_data.get(guild_id, {}).get(user_id, {"exp": 0, "level": 1, "current_title": "新手冒險者"})
        
        # 從 SQLite 讀取最新 SU幣餘額
        su_coins = get_wallet_balance(user_id)
        
        level = user.get("level", 1)
        next_level_exp = 50 * (level ** 2) - 50 * level

        embed = discord.Embed(title=f"{target.display_name} 的冒險者檔案", color=0x3498DB)
        embed.add_field(name="目前稱號", value=user.get("current_title", "新手冒險者"), inline=False)
        embed.add_field(name="等級 / 經驗值", value=f"Lv. {level} ({user['exp']} / {next_level_exp} XP)", inline=True)
        embed.add_field(name="SU 幣資產", value=f"{su_coins} SU幣", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="商店", description="開啟 SpiritVale 公會福利社，選購專屬稱號")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="SpiritVale 公會福利社",
            description="歡迎來到公會商店！所有稱號皆為 **30天租賃制**（再次購買可直接續約延長期限），購買後將自動從 SQLite 錢包扣除 **SU 幣** 並賦予對應身分組與顏色！",
            color=0xE74C3C
        )
        embed.add_field(name="價格級距", value="• **500 SU幣**：日常幹話系列 (30天)\n• **1,500 SU幣**：社畜悲傷系列 (30天)\n• **4,000 SU幣**：神級大老整活系列 (30天)", inline=False)
        view = ShopView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ProfileShopCog(bot))
