# ==================================================
# 檔案名稱：cogs/voice.py
# 檔案用途：語音陪伴時數、XP與SU幣自動發放系統（完全對應 SQLite 資料庫）
# ==================================================

import discord
from discord.ext import commands, tasks
from utils.level_helper import add_user_xp
from utils.economy_helper import update_user_coins
from utils.database import get_db_connection  # 🛡️ 引入統一的絕對路徑連線工具

class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_reward_loop.start()

    def cog_unload(self):
        self.voice_reward_loop.cancel()

    @tasks.loop(minutes=2.0)
    async def voice_reward_loop(self):
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                # 過濾機器人
                valid_members = [m for m in vc.members if not m.bot]
                # 語音頻道內至少要有 2 人（含）以上才計算獎勵，避免單人掛機刷時數
                if len(valid_members) < 2:
                    continue

                for member in valid_members:
                    # 檢查是否處於靜音或耳機靜音狀態
                    if not member.voice or member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf:
                        continue

                    user_id = member.id
                    user_id_str = str(member.id)
                    user_name = member.display_name

                    # 1. 發放 XP 與 SU 幣（每 2 分鐘獲得：+2 XP ｜ +1 SU 幣）
                    add_user_xp(user_id_str, user_name, xp_amount=2)
                    update_user_coins(user_id_str, user_name, amount=1)

                    # 2. 直接寫入 SQLite 資料庫的 voice_hours
                    conn = get_db_connection()
                    cursor = conn.cursor()

                    # 確保使用者存在於 member_levels 中
                    cursor.execute("""
                        INSERT OR IGNORE INTO member_levels (discord_id, level, su_coins, messages_count, voice_hours, exp, max_exp)
                        VALUES (?, 1, 0, 0, 0.0, 0, 100)
                    """, (user_id,))

                    # 累加語音時數（每 2 分鐘 = 2 / 60 小時）
                    cursor.execute("""
                        UPDATE member_levels 
                        SET voice_hours = ROUND(voice_hours + ?, 2)
                        WHERE discord_id = ?
                    """, (2.0 / 60.0, user_id))

                    # 同步更新 users 表格的最後活躍時間
                    cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE discord_id = ?", (user_id,))
                    
                    conn.commit()
                    conn.close()

    @voice_reward_loop.before_loop
    async def before_voice_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
