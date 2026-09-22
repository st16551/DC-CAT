# ==================================================
# 檔案名稱：economy.py
# 檔案用途：公會純資產/錢包核心模組（專責管理 SU 幣資產、幹部調幣與防負數安全機制）
# ==================================================

import discord
from discord import app_commands
from discord.ext import commands
from utils.database import load_data, save_data

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
        data = load_data()
        if "economy_system" not in data:
            data["economy_system"] = {}
        
        economy = data["economy_system"]
        if user_id not in economy:
            economy[user_id] = {"coins": 0, "name": member.display_name}

        # 嚴格防呆：透過 max(0, ...) 確保餘額絕對不會被扣到負數
        new_balance = max(0, economy[user_id]["coins"] + amount)
        economy[user_id]["coins"] = new_balance
        economy[user_id]["name"] = member.display_name

        save_data(data)

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
