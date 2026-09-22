# ==================================================
# 檔案名稱：voice.py
# 檔案用途：語音陪伴模組（背景定時發放 XP 與 SU 幣，內建防掛機與單人孤立保護）
# ==================================================

import discord
from discord.ext import commands, tasks
from utils.level_helper import add_user_xp
from utils.economy_helper import update_user_coins

class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_reward_loop.start() # 啟動背景每分鐘結算任務

    def cog_unload(self):
        self.voice_reward_loop.cancel()

    @tasks.loop(minutes=1.0)
    async def voice_reward_loop(self):
        """每分鐘掃描所有語音頻道中的成員，發放被動陪伴獎勵"""
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                # 排除沒有人的頻道，或只有 1 個人的頻道（避免開小號或單人孤立掛網刷獎勵）
                valid_members = [m for m in vc.members if not m.bot]
                if len(valid_members) < 2:
                    continue

                for member in valid_members:
                    # 🛡️ 防掛機保護：如果成員處於靜音 (Muted) 或自閉麥 (Deafened) 狀態，則不予發放獎勵
                    if member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf:
                        continue

                    user_id = str(member.id)
                    user_name = member.display_name

                    # 🌟 語音被動產出（精算控制通膨）：
                    # 每分鐘獲得：+1 XP ｜ +0.5 SU 幣 (或每兩分鐘發一次，這裡設定每分鐘給少量以維持穩定)
                    add_user_xp(user_id, user_name, xp_amount=1)
                    
                    # 為了避免小數點，我們設定每分鐘發 1 枚 SU 幣（或你可以調整）
                    update_user_coins(user_id, user_name, amount=1)

    @voice_reward_loop.before_loop
    async def before_voice_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
