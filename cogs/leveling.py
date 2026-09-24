# ==================================================
# 檔案名稱：cogs/leveling.py
# 檔案用途：公會經驗值、等級、訊息計數與個人面板模組（完全對應 SQLite 資料庫）
# ==================================================

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import random
from utils.database import get_db_connection  # 🛡️ 引入統一的絕對路徑連線工具

class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        user_name = message.author.display_name

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. 確保該會員在 member_levels 與 users 裡面有基本紀錄
        cursor.execute("INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (user_id,))
        cursor.execute("""
            INSERT OR IGNORE INTO member_levels (discord_id, level, su_coins, messages_count, voice_hours, exp, max_exp)
            VALUES (?, 1, 0, 0, 0.0, 0, 100)
        """, (user_id,))

        # 2. 累加文字發言數
        cursor.execute("""
            UPDATE member_levels 
            SET messages_count = messages_count + 1 
            WHERE discord_id = ?
        """, (user_id,))
        
        # 更新最後活躍時間
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE discord_id = ?", (user_id,))
        conn.commit()

        # 3. 檢查冷卻時間（避免洗頻洗經驗）
        if user_id in self.cooldowns:
            conn.close()
            return

        # 4. 處理經驗值與升級
        cursor.execute("SELECT level, exp, max_exp FROM member_levels WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            level, xp, max_exp = row["level"], row["exp"], row["max_exp"]
            
            xp_gain = random.randint(10, 20)
            xp += xp_gain
            leveled_up = False
            new_level = level

            # 檢查是否達到升級門檻
            if xp >= max_exp:
                new_level += 1
                xp -= max_exp
                max_exp = int(max_exp * 1.2)  # 每升一級提高升級門檻
                leveled_up = True

            cursor.execute("""
                UPDATE member_levels 
                SET level = ?, exp = ?, max_exp = ? 
                WHERE discord_id = ?
            """, (new_level, xp, max_exp, user_id))
            conn.commit()

            if leveled_up:
                try:
                    await message.channel.send(
                        f"🎉 恭喜 {message.author.mention} 升到了 **Lv.{new_level}**！"
                    )
                except discord.HTTPException:
                    pass

        conn.close()

        # 設定 60 秒冷卻
        self.cooldowns.add(user_id)
        self.bot.loop.create_task(self.remove_cooldown(user_id, 60))

    async def remove_cooldown(self, user_id: int, delay: int):
        await asyncio.sleep(delay)
        self.cooldowns.discard(user_id)

    @app_commands.command(
        name="我的面板", 
        description="查看你在公會裡的完整個人檔案（等級、SU幣、時數、訊息次數）"
    )
    async def my_profile(self, interaction: discord.Interaction):
        user = interaction.user
        user_id = user.id

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 從 SQLite 抓取該成員的完整數據
        cursor.execute("""
            SELECT level, su_coins, messages_count, voice_hours, exp, max_exp 
            FROM member_levels 
            WHERE discord_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            level = row["level"]
            coins = row["su_coins"]
            msg_count = row["messages_count"]
            voice_hours = row["voice_hours"]
            xp = row["exp"]
            max_exp = row["max_exp"]
        else:
            # 預設值（防呆）
            level, coins, msg_count, voice_hours, xp, max_exp = 1, 0, 0, 0.0, 0, 100

        # 計算進度條
        percentage = min(xp / max_exp, 1.0) if max_exp > 0 else 0
        filled_blocks = int(percentage * 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks

        embed = discord.Embed(
            title=f"👤 {user.display_name} 的公會個人面板",
            description="以下為你在公會中的各項成長數據：",
            color=discord.Color.teal()
        )
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(name="📊 目前等級", value=f"**Lv. {level}**", inline=True)
        embed.add_field(name="💰 SU 幣資產", value=f"**{coins}** 枚", inline=True)
        embed.add_field(name="💬 文字發言數", value=f"**{msg_count}** 次", inline=True)
        embed.add_field(name="🎧 語音陪伴時數", value=f"**{voice_hours:.1f}** 小時", inline=True)
        embed.add_field(name="📈 經驗值進度", value=f"`{progress_bar}`\n**{xp} / {max_exp} XP**", inline=False)

        embed.set_footer(text="DC-CAT 模組化管理系統 • 只有你看得見此面板")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="重製等級資料", 
        description="[幹部專用] 一鍵清空所有人的等級與經驗值"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_level(self, interaction: discord.Interaction):
        conn = get_db_connection()
        cursor = conn.cursor()
        # 將所有人的等級歸回 1，經驗歸 0
        cursor.execute("UPDATE member_levels SET level = 1, exp = 0, max_exp = 100")
        conn.commit()
        conn.close()

        await interaction.response.send_message("🗑️ **【系統重製完成】** 所有人的等級與經驗值已全數歸零！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LevelingCog(bot))
