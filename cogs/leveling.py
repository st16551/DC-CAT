# ==================================================
# 檔案名稱：leveling.py
# 檔案用途：公會等級經驗值系統與整合型個人面板（支援發言加 XP、冷卻、個人面板與一鍵重製）
# ==================================================

import asyncio
from datetime import datetime
import random
import discord
from discord import app_commands
from discord.ext import commands
from utils.database import load_data, save_data

class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = str(message.author.id)
        user_name = message.author.display_name

        if user_id in self.cooldowns:
            return

        data = load_data()
        if "leveling_system" not in data:
            data["leveling_system"] = {}

        users = data["leveling_system"]
        if user_id not in users:
            users[user_id] = {"name": user_name, "xp": 0, "level": 1}

        # 隨機獲得 10 ~ 20 點經驗值
        xp_gain = random.randint(10, 20)
        users[user_id]["xp"] += xp_gain
        users[user_id]["name"] = user_name

        current_xp = users[user_id]["xp"]
        current_level = users[user_id]["level"]
        xp_needed = current_level * 100

        # 檢查是否升級
        if current_xp >= xp_needed:
            users[user_id]["level"] += 1
            users[user_id]["xp"] -= xp_needed
            
            try:
                await message.channel.send(
                    f"🎉 恭喜 {message.author.mention} 升到了 **Lv.{current_level + 1}**！"
                )
            except discord.HTTPException:
                pass

        save_data(data)

        # 加入 60 秒冷卻
        self.cooldowns.add(user_id)
        self.bot.loop.create_task(self.remove_cooldown(user_id, 60))

    async def remove_cooldown(self, user_id: str, delay: int):
        await asyncio.sleep(delay)
        self.cooldowns.discard(user_id)

    @app_commands.command(
        name="我的面板", 
        description="查看你在公會裡的完整個人檔案（等級、SU幣、時數、訊息次數）"
    )
    async def my_profile(self, interaction: discord.Interaction):
        user = interaction.user
        user_id = str(user.id)

        data = load_data()
        
        # 讀取等級資料
        levels = data.get("leveling_system", {})
        user_level_data = levels.get(user_id, {"level": 1, "xp": 0})
        level = user_level_data["level"]
        xp = user_level_data["xp"]
        xp_needed = level * 100

        # 讀取經濟與活躍時數資料（若未來模組尚未建立，預設為 0）
        economy = data.get("economy_system", {})
        coins = economy.get(user_id, {}).get("coins", 0)

        activity = data.get("activity_system", {})
        voice_hours = activity.get(user_id, {}).get("voice_hours", 0.0)
        msg_count = activity.get(user_id, {}).get("msg_count", 0)

        # 製作經驗值進度條
        percentage = min(xp / xp_needed, 1.0)
        filled_blocks = int(percentage * 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks

        embed = discord.Embed(
            title=f"👤 {user.display_name} 的公會個人面板",
            description="以下為你在公會中的各項成長數據：",
            color=discord.Color.teal()
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        # 填入各項數據
        embed.add_field(name="📊 目前等級", value=f"**Lv. {level}**", inline=True)
        embed.add_field(name="💰 SU 幣資產", value=f"**{coins}** 枚", inline=True)
        embed.add_field(name="💬 文字發言數", value=f"**{msg_count}** 次", inline=True)
        
        embed.add_field(name="🎧 語音陪伴時數", value=f"**{voice_hours:.1f}** 小時", inline=True)
        embed.add_field(name="📈 經驗值進度", value=f"`{progress_bar}`\n**{xp} / {xp_needed} XP**", inline=False)

        embed.set_footer(text="DC-CAT 模組化管理系統 • 只有你看得見此面板")
        
        # ephemeral=True 確保只有自己看得到
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="重製等級資料", 
        description="[幹部專用] 一鍵清空所有人的等級與經驗值"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_level(self, interaction: discord.Interaction):
        data = load_data()
        if "leveling_system" in data:
            data["leveling_system"] = {}
            save_data(data)
            await interaction.response.send_message("🗑️ **【系統重製完成】** 所有人的等級與經驗值已全數歸零！", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ 目前沒有找到任何等級資料。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LevelingCog(bot))
