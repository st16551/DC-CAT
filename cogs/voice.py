import discord
from discord.ext import commands, tasks
from utils.database import load_data, save_data
from utils.level_helper import add_user_xp
from utils.economy_helper import update_user_coins

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
                valid_members = [m for m in vc.members if not m.bot]
                if len(valid_members) < 2:
                    continue

                for member in valid_members:
                    if not member.voice or member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf:
                        continue

                    user_id = str(member.id)
                    user_name = member.display_name

                    # 每 2 分鐘獲得：+2 XP ｜ +1 SU 幣
                    add_user_xp(user_id, user_name, xp_amount=2)
                    update_user_coins(user_id, user_name, amount=1)

                    data = load_data()
                    if "activity_system" not in data:
                        data["activity_system"] = {}
                    
                    activity = data["activity_system"]
                    if user_id not in activity:
                        activity[user_id] = {"voice_hours": 0.0, "msg_count": 0, "name": user_name}

                    activity[user_id]["voice_hours"] += 2.0 / 60.0
                    activity[user_id]["voice_hours"] = round(activity[user_id]["voice_hours"], 2)
                    activity[user_id]["name"] = user_name
                    
                    save_data(data)

    @voice_reward_loop.before_loop
    async def before_voice_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
