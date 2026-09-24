import asyncio
import random
import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_db_connection  # 引入共用的資料庫連線函式

class GiveawayView(discord.ui.View):
    def __init__(self, cog, message_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.message_id = message_id

    @discord.ui.button(
        label="🎉 點擊參與抽獎",
        style=discord.ButtonStyle.green,
        custom_id="persistent_join_giveaway_btn"
    )
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 使用共用連線
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT participants, ended FROM giveaways WHERE message_id = ?", (self.message_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            await interaction.response.send_message("❌ 找不到此抽獎活動的資料！", ephemeral=True)
            return
            
        participants_str, ended = row['participants'], row['ended']
        if ended == 1:
            conn.close()
            await interaction.response.send_message("⚠️ 這次抽獎已經結束囉！", ephemeral=True)
            return

        participants = set(map(int, participants_str.split(","))) if participants_str else set()

        if interaction.user.id in participants:
            conn.close()
            await interaction.response.send_message("⚠️ 你已經參加過這次抽獎囉！請耐心等候開獎。", ephemeral=True)
        else:
            participants.add(interaction.user.id)
            new_participants_str = ",".join(map(str, participants))
            cursor.execute("UPDATE giveaways SET participants = ? WHERE message_id = ?", (new_participants_str, self.message_id))
            conn.commit()
            conn.close()
            
            await interaction.response.send_message(
                f"✅ 成功參與抽獎！目前累積參與人數：**{len(participants)}** 人",
                ephemeral=True,
            )

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.check_pending_giveaways())

    async def check_pending_giveaways(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = discord.utils.utcnow().timestamp()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT message_id, channel_id, prize, winners_count, end_timestamp, participants FROM giveaways WHERE ended = 0 AND end_timestamp <= ?", (now,))
            expired_giveaways = cursor.fetchall()
            conn.close()

            for giveaway in expired_giveaways:
                await self.end_giveaway_by_data(giveaway['message_id'], giveaway['channel_id'], giveaway['prize'], giveaway['winners_count'], giveaway['participants'])

            await asyncio.sleep(10)

    async def end_giveaway_by_data(self, message_id: int, channel_id: int, prize: str, winners_count: int, participants_str: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
        conn.commit()
        conn.close()

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            return

        participants_list = list(map(int, participants_str.split(","))) if participants_str else []
        view = GiveawayView(self, message_id)
        for child in view.children:
            child.disabled = True

        if not participants_list:
            end_embed = discord.Embed(title="🎁 抽獎活動已結束", description=f"**獎品**：`{prize}`\n\n❌ 很可惜，本次活動沒有人參與，流標！", color=discord.Color.red())
            await message.edit(embed=end_embed, view=view)
            return

        actual_winners_count = min(winners_count, len(participants_list))
        winner_ids = random.sample(participants_list, actual_winners_count)
        winner_mentions = [f"<@{uid}>" for uid in winner_ids]

        end_embed = discord.Embed(
            title="🎁 抽獎活動已結束！得獎名單出爐",
            description=f"**獎品**：`{prize}`\n**總參與人數**：`{len(participants_list)} 人`\n\n🏆 **恭喜以下得獎者**：\n" + "\n".join(winner_mentions),
            color=discord.Color.green(),
        )
        await message.edit(embed=end_embed, view=view)
        await channel.send(f"🎊 恭喜 {', '.join(winner_mentions)} 獲得了 **{prize}**！請私訊管理員領取獎品！")

    @app_commands.command(name="抽獎", description="【管理員】發起一個抽獎活動")
    @app_commands.checks.has_permissions(administrator=True)
    async def start_giveaway(self, interaction: discord.Interaction, prize: str, winners_count: int, duration_minutes: int):
        await interaction.response.send_message("🎉 抽獎活動已成功建立並發布！", ephemeral=True)
        end_timestamp = discord.utils.utcnow().timestamp() + (duration_minutes * 60)

        embed = discord.Embed(
            title="🎁 伺服器限時抽獎活動！",
            description=f"**獎品內容**：`{prize}`\n**得獎名額**：`{winners_count} 名`\n**結束時間**：`{duration_minutes} 分鐘後`\n\n👇 **請點擊下方綠色按鈕參與抽獎！**",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"發起人：{interaction.user.name}")

        message = await interaction.channel.send(embed=embed)
        view = GiveawayView(self, message.id)
        await message.id_edit(view=view) if hasattr(message, 'id_edit') else await message.edit(view=view)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO giveaways (message_id, channel_id, prize, winners_count, end_timestamp, participants, ended)
            VALUES (?, ?, ?, ?, ?, '', 0)
        """, (message.id, interaction.channel.id, prize, winners_count, end_timestamp))
        conn.commit()
        conn.close()

async def setup(bot):
    cog = GiveawayCog(bot)
    await bot.add_cog(cog)
    bot.add_view(GiveawayView(cog, message_id=0))
