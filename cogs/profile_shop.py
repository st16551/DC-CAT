# ==================================================
# 檔案名稱：cogs/profile_shop.py
# 檔案用途：個人稱號商店（以 utils.DATA_FILE 持久化購買紀錄，SU 幣扣款走同一錢包）
# ==================================================

import json
import os

import discord
from discord import app_commands
from discord.ext import commands

from utils import DATA_FILE, load_data, save_data
from utils.economy_helper import get_wallet_balance, modify_balance

SHOP_ITEMS = {
    "rookie": {"name": "🌱 公會萌新", "price": 80},
    "active": {"name": "🔥 活躍分子", "price": 180},
    "raider": {"name": "⚔️ 爬塔先鋒", "price": 260},
    "veteran": {"name": "🏆 資深幹部氣場", "price": 400},
}


def _load_shop_store() -> dict:
    store = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                store = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            store = load_data() or {}
    else:
        store = load_data() or {}
    if not isinstance(store, dict):
        store = {}
    store.setdefault("profile_shop", {})
    return store


def _save_shop_store(store: dict):
    save_data(store)


class ProfileShopView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        for item_id, meta in SHOP_ITEMS.items():
            button = discord.ui.Button(
                label=f"{meta['name']} ({meta['price']})",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile_shop_buy_{item_id}",
            )
            button.callback = self._make_callback(item_id)
            self.add_item(button)

    def _make_callback(self, item_id: str):
        async def _buy(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("❌ 這不是你的商店面板。", ephemeral=True)
                return

            item = SHOP_ITEMS[item_id]
            user_id = str(interaction.user.id)
            balance = get_wallet_balance(user_id)
            if balance < item["price"]:
                await interaction.response.send_message(
                    f"❌ SU 幣不足。購買【{item['name']}】需要 `{item['price']}`，目前 `{balance}`。",
                    ephemeral=True,
                )
                return

            store = _load_shop_store()
            profile = store["profile_shop"].setdefault(user_id, {"owned": [], "equipped": None})
            owned = profile.setdefault("owned", [])
            if item_id in owned:
                profile["equipped"] = item_id
                _save_shop_store(store)
                await interaction.response.send_message(
                    f"✅ 你已擁有【{item['name']}】，已重新裝備。",
                    ephemeral=True,
                )
                return

            result = modify_balance(user_id, interaction.user.display_name, -item["price"])
            if not result.get("success"):
                await interaction.response.send_message("❌ 扣款失敗，請稍後再試。", ephemeral=True)
                return

            owned.append(item_id)
            profile["equipped"] = item_id
            _save_shop_store(store)
            await interaction.response.send_message(
                f"✅ 已花費 `{item['price']}` SU 幣購買並裝備【{item['name']}】！\n餘額：`{result['new_balance']}`",
                ephemeral=True,
            )

        return _buy


class ProfileShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="個人商店", description="用 SU 幣購買並裝備個人稱號")
    async def open_profile_shop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        store = _load_shop_store()
        profile = store.get("profile_shop", {}).get(user_id, {})
        equipped_id = profile.get("equipped")
        equipped_name = SHOP_ITEMS.get(equipped_id, {}).get("name", "尚未裝備")
        owned_ids = profile.get("owned") or []
        owned_names = "、".join(SHOP_ITEMS[i]["name"] for i in owned_ids if i in SHOP_ITEMS) or "尚無"

        embed = discord.Embed(
            title="🛍️ 個人稱號商店",
            description=(
                f"目前餘額：`{get_wallet_balance(user_id)}` SU 幣\n"
                f"已裝備：{equipped_name}\n"
                f"已擁有：{owned_names}\n\n"
                "點擊下方按鈕即可購買；若已擁有則會改為裝備。"
            ),
            color=discord.Color.purple(),
        )
        embed.set_footer(text=f"資料檔：{os.path.basename(DATA_FILE)}")
        await interaction.response.send_message(
            embed=embed, view=ProfileShopView(interaction.user.id), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ProfileShopCog(bot))
