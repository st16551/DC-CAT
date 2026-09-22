# ==================================================
# 檔案名稱：economy.py
# 檔案用途：公會純資產/錢包指令模組（透過 utils/economy_helper 執行底層財務操作）
# ==================================================

import discord
from discord import app_commands
from discord.ext import commands
from utils.database import load_data, save_data
from utils.economy_helper import update_user_coins  # 引入我們剛才建立的共用經濟核心

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="調整金幣", 
        description="[幹部專用] 手動增加或扣除指定成員的 SU 幣（內建防負數安全底線）"
    )
    @app_commands.describe(member="目標成員", amount="調整數量（正數為發放，負數為扣除）")
    @app_commands.checks.has_permissions(administrator=True)
    async def adjust_coins(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        user_id = str(member.id)
        user_name = member.display_name

        # 直接呼叫共用經濟核心來處理加減與防負數
        result = update_user_coins(user_id, user_name, amount)
        new_balance = result["new_balance"]

        action_str = "發放" if amount >= 0 else "扣除"
        await interaction.response.send_message(
            f"✅ **【幹部財務調整】** 已成功對 {member.mention} 進行{action_str} `{abs(amount)}` 枚 SU 幣。\n目前該成員最新餘額：`{new_balance}` 枚。",
            ephemeral=True
        )

    @app_commands.command(
        name="重製經濟", 
        description="[幹部專用] 一鍵清空所有人的 SU 幣資產"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_economy(self, interaction: discord.Interaction):
        data = load_data()
        if "economy_system" in data:
            data["economy_system"] = {}
            save_data(data)
            await interaction.response.send_message("🗑️ **【系統重製完成】** 所有成員的 SU 幣資產已全數歸零！", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ 目前沒有找到任何經濟資料。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
