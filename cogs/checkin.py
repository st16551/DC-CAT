# ==================================================
# 檔案名稱：checkin.py
# 檔案用途：公會簽到模組（具備永久按鈕、SQLite 持久化、一鍵重製與經驗/SU幣保底機制）
# ==================================================

from datetime import datetime
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from utils.level_helper import add_user_xp
from utils.economy_helper import update_user_coins

DB_FILE = "guild_database.db"

def init_checkin_table():
    """確保資料庫中存在簽到表格"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkin_system (
            discord_id INTEGER PRIMARY KEY,
            name TEXT,
            last_date TEXT,
            streak INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# 模組載入時自動檢查並建立表格
init_checkin_table()


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
        user_id = interaction.user.id
        user_name = interaction.user.display_name
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 連線 SQLite 資料庫
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 查詢使用者簽到狀態
        cursor.execute("SELECT last_date, streak FROM checkin_system WHERE discord_id = ?", (user_id,))
        record = cursor.fetchone()

        if record:
            last_date, streak = record
            if last_date == today_str:
                conn.close()
                return await interaction.response.send_message("⚠️ 你今天已經簽到過了，明天請早！", ephemeral=True)
            streak += 1
        else:
            streak = 1

        # 更新或插入最新簽到資料到 SQLite
        cursor.execute("""
            INSERT INTO checkin_system (discord_id, name, last_date, streak)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                name = excluded.name,
                last_date = excluded.last_date,
                streak = excluded.streak
        """, (user_id, user_name, today_str, streak))
        
        conn.commit()
        conn.close()

        # 核心保底發放：150 XP ｜ 50 枚 SU 幣 + 連續簽到加碼（上限額外 50 枚）
        xp_result = add_user_xp(str(user_id), user_name, xp_amount=150)
        bonus_coins = min(streak * 2, 50)
        total_coins_gain = 50 + bonus_coins
        update_user_coins(str(user_id), user_name, amount=total_coins_gain)

        msg = f"✅ 簽到成功！連續簽到天數：**{streak}** 天\n🎁 獲得獎勵：`+150 XP` ｜ `+{total_coins_gain} SU 幣`"
        if xp_result["leveled_up"]:
            msg += f"\n🎉 恭喜升到了 **Lv.{xp_result['new_level']}**！"

        await interaction.response.send_message(msg, ephemeral=True)


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
            description="點擊下方按鈕即可完成今日簽到。\n*(系統具備重啟不失效與 SQLite 雲端備份功能)*",
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
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 清空 checkin_system 表格資料
        cursor.execute("DELETE FROM checkin_system")
        conn.commit()
        conn.close()
        
        await interaction.response.send_message("🗑️ **【系統重製完成】** 所有人的簽到紀錄與天數已全數歸零！", ephemeral=True)

async def setup(bot):
    # 註冊永久 View，確保機器人開機時能喚醒按鈕
    bot.add_view(PersistentCheckinView())
    await bot.add_cog(CheckinCog(bot))
