import discord
from discord import app_commands
from discord.ext import commands
from utils.economy_helper import update_user_coins
from utils.database import DB_FILE
import sqlite3

class QuestBoardView(discord.ui.View):
    def __init__(self, author: discord.User, title: str, reward: int, max_slots: int):
        super().__init__(timeout=None)
        self.author = author
        self.quest_title = title
        self.reward = reward
        self.max_slots = max_slots
        self.takers: list[discord.User] = []
        self.is_closed = False

    def _build_embed(self) -> discord.Embed:
        status = "[已結案]" if self.is_closed else "[任務懸賞中]"
        color = discord.Color.red() if self.is_closed else discord.Color.gold()
        takers_list = "\n".join([u.mention for u in self.takers]) if self.takers else "尚無人接取"
        
        embed = discord.Embed(
            title=f"公會懸賞任務 {status}",
            description=f"任務內容：{self.quest_title}\n"
                        f"發布者：{self.author.mention}\n"
                        f"懸賞報酬：`{self.reward} SU幣`\n"
                        f"名額限制：{len(self.takers)} / {self.max_slots} 人\n\n"
                        f"目前接取成員：\n{takers_list}",
            color=color
        )
        return embed

    @discord.ui.button(label="接取任務", style=discord.ButtonStyle.success, custom_id="accept_quest_btn")
    async def accept_quest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("此任務已經結案，無法再接取！", ephemeral=True)
            return
        
        user = interaction.user
        if user.id == self.author.id:
            await interaction.response.send_message("發布者不能自己接取自己的任務！", ephemeral=True)
            return
        
        if user in self.takers:
            await interaction.response.send_message("你已經接取過這個任務了！", ephemeral=True)
            return

        if len(self.takers) >= self.max_slots:
            await interaction.response.send_message("此任務名額已滿！", ephemeral=True)
            return

        self.takers.append(user)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="結案確認", style=discord.ButtonStyle.primary, custom_id="close_quest_btn")
    async def close_quest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("只有任務發布者或管理員可以結案！", ephemeral=True)
            return

        if self.is_closed:
            await interaction.response.send_message("此任務已經結案過了！", ephemeral=True)
            return

        # 1. 如果無人接取，退回保證金給發布者
        if not self.takers:
            update_user_coins(str(self.author.id), self.author.name, self.reward)
            self.is_closed = True
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=self._build_embed(), view=self)
            await interaction.followup.send("任務無人接取而關閉，保證金已全數退回發布者。")
            return

        # 2. 有人接取的情況：發放 SU 幣報酬給所有接取者
        for taker in self.takers:
            update_user_coins(str(taker.id), taker.name, self.reward)

        self.is_closed = True
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=self._build_embed(), view=self)
        await interaction.followup.send(f"任務已成功結案！懸賞獎勵已自動發放給 {len(self.takers)} 位接取成員！")

class QuestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="發布任務", description="發布公會懸賞任務")
    @app_commands.describe(title="任務內容說明與標題", reward="懸賞總 SU 幣", slots="需要接取人數名額")
    async def post_quest(self, interaction: discord.Interaction, title: str, reward: int, slots: int):
        if reward <= 0 or slots <= 0:
            await interaction.response.send_message("懸賞獎勵與名額限制必須大於 0！", ephemeral=True)
            return

        user_id_str = str(interaction.user.id)
        user_name = interaction.user.name

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT su_coins FROM member_levels WHERE discord_id = ?", (interaction.user.id,))
        row = cursor.fetchone()
        current_coins = row[0] if row else 0
        conn.close()

        if current_coins < reward:
            await interaction.response.send_message(f"你的 SU 幣不足！發布此任務需要保證金 `{reward} SU幣`。（目前擁有: `{current_coins}`）", ephemeral=True)
            return

        # 扣除發布者的保證金
        update_user_coins(user_id_str, user_name, -reward)

        view = QuestBoardView(author=interaction.user, title=title, reward=reward, max_slots=slots)
        embed = view._build_embed()
        await interaction.response.send_message(content=f"**{interaction.user.mention} 發布了新的公會懸賞任務！**", embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(QuestCog(bot))
