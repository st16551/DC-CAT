# ==================================================
# 檔案名稱：voice.py
# 檔案用途：公會語音時數高級統計與防掛機系統（支援防靜音掛機、自動轉化經驗值與面板連動）
# ==================================================

from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.database import load_data, save_data

class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 記錄目前正在語音中的有效使用者 {user_id: 進入時間}
        self.active_voice_users = {}
        # 啟動背景定期檢查任務（每 60 秒檢查一次語音狀態並發放獎勵）
        self.voice_check_task.start()

    def cog_unload(self):
        self.voice_check_task.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        user_id = str(member.id)
        now = datetime.now()

        # 離開語音或是被移動到無頻道處
        if before.channel is not None and after.channel is None:
            if user_id in self.active_voice_users:
                self.active_voice_users.pop(user_id)

        # 加入語音或是切換頻道
        elif after.channel is not None:
            # 檢查是否符合有效計時條件（未自己靜音、未拒聽）
            if not member.voice.self_mutes and not member.voice.self_deaf:
                if user_id not in self.active_voice_users:
                    self.active_voice_users[user_id] = now
            else:
                # 如果處於靜音掛機狀態，則移除計時
                if user_id in self.active_voice_users:
                    self.active_voice_users.pop(user_id)

    @tasks.loop(minutes=1.0)
    async def voice_check_task(self):
        """背景迴圈：每分鐘自動檢查在語音中的成員，防掛機並自動累積時數與經驗值"""
        if not self.active_voice_users:
            return

        data = load_data()
        if "activity_system" not in data:
            data["activity_system"] = {}
        if "leveling_system" not in data:
            data["leveling_system"] = {}

        activity = data["activity_system"]
        levels = data["leveling_system"]

        for user_id in list(self.active_voice_users.keys()):
            # 嘗試從快取中取得成員物件以檢查最新狀態
            found = False
            for guild in self.bot.guilds:
                member = guild.get_member(int(user_id))
                if member and member.voice and member.voice.channel:
                    found = True
                    # 防掛機檢查：如果成員將自己靜音或擴音靜音，不予計算該分鐘時數
                    if member.voice.self_mute or member.voice.self_deaf:
                        continue
                    
                    # 檢查是否單獨一人在頻道（可選：若希望有人陪才計時，保留此檢查）
                    if len(member.voice.channel.members) <= 1:
                        continue

                    user_name = member.display_name
                    
                    # 初始化活動數據
                    if user_id not in activity:
                        activity[user_id] = {"msg_count": 0, "voice_hours": 0.0, "name": user_name}
                    
                    # 每 1 分鐘 = 1/60 小時
                    activity[user_id]["voice_hours"] = round(activity[user_id]["voice_hours"] + (1 / 60.0), 2)
                    activity[user_id]["name"] = user_name

                    # 語音同時獎勵經驗值（每分鐘獲得 2 點 XP）
                    if user_id not in levels:
                        levels[user_id] = {"name": user_name, "xp": 0, "level": 1}
                    
                    levels[user_id]["xp"] += 2
                    levels[user_id]["name"] = user_name

                    # 簡單檢查升級
                    lvl = levels[user_id]["level"]
                    xp = levels[user_id]["xp"]
                    needed = lvl * 100
                    if xp >= needed:
                        levels[user_id]["level"] += 1
                        levels[user_id]["xp"] -= needed

                    break
            
            if not found:
                # 若成員已經不在語音中，清除紀錄
                self.active_voice_users.pop(user_id, None)

        save_data(data)

    @voice_check_task.before_loop
    async def before_voice_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="重製語音時數", 
        description="[幹部專用] 一鍵清空所有人的語音陪伴時數"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_voice(self, interaction: discord.Interaction):
        data = load_data()
        if "activity_system" in data:
            for uid in data["activity_system"]:
                data["activity_system"][uid]["voice_hours"] = 0.0
            save_data(data)
            await interaction.response.send_message("🗑️ **【系統重製完成】** 所有人的語音陪伴時數已全數歸零！", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ 目前沒有找到任何活動紀錄資料。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
