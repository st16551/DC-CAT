import discord
from discord.ext import commands

# 💡 請務必把這裡換成你 Discord 伺服器「歷史紀錄頻道」的真實 ID 數字！
ARCHIVE_CHANNEL_ID = 1548834766684426390


class TaskView(discord.ui.View):

    def __init__(self, task_title, task_desc, creator, bot, initial_assignee=None):
        super().__init__(timeout=None)
        self.task_title = task_title
        self.task_desc = task_desc
        self.creator = creator  # 發布者
        self.bot = bot
        
        self.designated_assignee = initial_assignee  # 原始指定的對象 (Member 物件或 None)

        # 負責幹部狀態初始化
        if initial_assignee:
            self.assignee_text = initial_assignee.mention
            self.is_claimed = True
        else:
            self.assignee_text = "尚未認領"
            self.is_claimed = False

        self.status = "進行中 ⏳"

    def update_embed(self, color=discord.Color.gold()):
        embed = discord.Embed(
            title=f"📌 幹部交辦事項：{self.task_title}",
            description=self.task_desc,
            color=color,
        )
        embed.add_field(name="👤 發布者", value=self.creator.mention, inline=True)
        
        # 顯示指定指派人
        designated_val = self.designated_assignee.mention if self.designated_assignee else "無 (自由認領)"
        embed.add_field(name="🎯 指定指派人", value=designated_val, inline=True)
        
        embed.add_field(name="📋 負責幹部", value=self.assignee_text, inline=False)
        embed.add_field(name="當前狀態", value=self.status, inline=False)
        embed.set_footer(text="小貓咪交辦管理系統")
        return embed

    @discord.ui.button(
        label="我要接取 🙋‍♂️",
        style=discord.ButtonStyle.primary,
        custom_id="claim_task_v3",
    )
    async def claim_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # 1. 發布任務的人不能自己接取自己的任務
        if interaction.user.id == self.creator.id:
            await interaction.response.send_message(
                "⚠️ 這是你發布的任務，不能自己指派給自己執行哦！", ephemeral=True
            )
            return

        # 2. 如果建立時有「指定指派人」
        if self.designated_assignee:
            if interaction.user.id != self.designated_assignee.id:
                await interaction.response.send_message(
                    f"⚠️ 此任務已指定指派給 {self.designated_assignee.mention}，其他人無法接取！", ephemeral=True
                )
                return

        # 3. 檢查是否已經被其他人認領
        if self.is_claimed and self.designated_assignee is None:
            await interaction.response.send_message(
                "⚠️ 這項任務已經有人接走了唷！", ephemeral=True
            )
            return

        # 執行接取動作
        self.assignee_text = interaction.user.mention
        self.is_claimed = True
        
        await interaction.message.edit(
            embed=self.update_embed(discord.Color.gold()), view=self
        )
        await interaction.response.send_message(
            f"🎉 成功認領任務：**{self.task_title}**！", ephemeral=True
        )

    @discord.ui.button(
        label="回報完成 ✅",
        style=discord.ButtonStyle.success,
        custom_id="complete_task_v3",
    )
    async def complete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # 防呆 1：尚未有人接取的任務不能結案
        if not self.is_claimed:
            await interaction.response.send_message(
                "⚠️ 這項任務目前還沒有人接取或認領，無法回報完成！", ephemeral=True
            )
            return

        # 防呆 2：權限檢查（只有負責人、發布者或管理員可以按結案）
        is_responsible = (self.designated_assignee and interaction.user.id == self.designated_assignee.id) or \
                         (self.assignee_text != "尚未認領" and interaction.user.mention in self.assignee_text)
        is_creator = (interaction.user.id == self.creator.id)
        is_admin = interaction.user.guild_permissions.administrator

        if not (is_responsible or is_creator or is_admin):
            await interaction.response.send_message(
                "❌ 只有【負責幹部】、【任務發布者】或【伺服器管理員】才能將此任務回報完成！", ephemeral=True
            )
            return

        self.status = f"已完工 ✨ (由 {interaction.user.mention} 確認)"
        completed_embed = self.update_embed(discord.Color.green())

        for child in self.children:
            child.disabled = True

        await interaction.message.edit(embed=completed_embed, view=self)
        await interaction.response.send_message(
            f"🏆 任務【{self.task_title}】已圓滿結案！", ephemeral=False
        )

        # 發送到備份頻道
        archive_channel = self.bot.get_channel(ARCHIVE_CHANNEL_ID)
        if archive_channel:
            archive_embed = discord.Embed(
                title=f"📁 已歸檔交辦事項：{self.task_title}",
                description=self.task_desc,
                color=discord.Color.blue(),
            )
            archive_embed.add_field(name="👤 發布者", value=self.creator.mention, inline=True)
            designated_val = self.designated_assignee.mention if self.designated_assignee else "無 (自由認領)"
            archive_embed.add_field(name="🎯 指定指派人", value=designated_val, inline=True)
            archive_embed.add_field(name="📋 執行幹部", value=self.assignee_text, inline=False)
            archive_embed.add_field(name="結案狀態", value=self.status, inline=False)
            archive_embed.set_footer(text="歷史紀錄自動備份")
            await archive_channel.send(embed=archive_embed)


class TaskCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="交辦", description="發布一項新的幹部交辦任務卡片"
    )
    @discord.app_commands.describe(
        title="任務標題",
        content="任務詳細說明與要求",
        assignee="（選填）直接指定負責執行的幹部",
    )
    async def create_task(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        assignee: discord.Member = None,
    ):
        view = TaskView(
            title, content, interaction.user, self.bot, initial_assignee=assignee
        )
        embed = view.update_embed(discord.Color.gold())
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=False
        )


async def setup(bot):
    await bot.add_cog(TaskCog(bot))
