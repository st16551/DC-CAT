# ==================================================
# 檔案名稱：checkin.py
# 檔案用途：公會簽到模組（具備永久按鈕、JSON 持久化與一鍵重製功能）
# ==================================================

from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
from utils.database import load_data, save_data

class PersistentCheckinView(discord.ui.View):
    """永久按鈕面板：timeout=None 確保機器人重開機後按鈕依然有效"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📅 點選進行今日簽到", 
        style=discord.ButtonStyle.green, 
        custom_id="persistent_checkin_button_id"
    )
    async def checkin_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 讀取 JSON 資料
        data = load_data()
        
        # 初始化結構 (確保 checkin 模組結構存在)
        if "checkin_system" not in data:
            data["checkin_system"] = {}
        
        user_records = data["checkin_system"]
        if user_id not in user_records:
            user_records[user_id] = {"name": user_name, "last_date": "", "streak": 0}

        # 檢查今天是否已經簽到過
        if user_records[user_id]["last_date"] == today_str:
            return await interaction.response.send_message("⚠️ 你今天已經簽到過了，明天請早！", ephemeral=True)

        # 更新簽到資料
        user_records[user_id]["last_date"] = today_str
        user_records[user_id]["streak"] += 1
        user_records[user_id]["name"] = user_name # 更新最新名稱

        # 寫回 JSON 檔案
        save_data(data)

        streak = user_records[user_id]["streak"]
        await interaction.response.send_message(f"✅ 簽到成功！連續簽到天數：**{streak}** 天", ephemeral=True)


class CheckinCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="建立簽到面板", 
        description="[幹部專用] 發送永久有效的簽到卡片"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_checkin(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📌 公會每日簽到中心",
            description="點擊下方按鈕即可完成今日簽到。\n*(系統具備重啟不失效與自動存檔功能)*",
            color=discord.Color.blue()
        )
        embed.set_footer(text="DC-CAT 模組化管理系統")
        
        view = PersistentCheckinView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 簽到面板已成功發送！", ephemeral=True)

    @app_commands.command(
        name="重製簽到資料", 
        description="[幹部專用] 一鍵清空所有人的簽到紀錄與連續天數"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_checkin(self, interaction: discord.Interaction):
        data = load_data()
        
        if "checkin_system" in data:
            # 清空簽到資料
            data["checkin_system"] = {}
            save_data(data)
            await interaction.response.send_message("🗑️ **【系統重製完成】** 所有人的簽到紀錄與天數已全數歸零！", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ 目前沒有找到任何簽到資料。", ephemeral=True)

async def setup(bot):
    # 註冊永久 View，確保機器人開機時能喚醒按鈕
    bot.add_view(PersistentCheckinView())
    await bot.add_cog(CheckinCog(bot))
