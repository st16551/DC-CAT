import discord
from discord.ext import commands

# 💡 請把這裡改成你 Discord 頻道 ID
ARCHIVE_CHANNEL_ID = 123456789012345678


class TaskView(discord.ui.View):

  def __init__(self, task_title, task_desc, creator, bot):
    super().__init__(timeout=None)
    self.task_title = task_title
    self.task_desc = task_desc
    self.creator = creator
    self.bot = bot
    self.assignee = "尚未認領"
    self.status = "進行中 ⏳"

  def update_embed(self, color=discord.Color.gold()):
    embed = discord.Embed(
        title=f"📌 幹部交辦事項：{self.task_title}",
        description=self.task_desc,
        color=color,
    )
    embed.add_field(name="指派人", value=self.creator.mention, inline=True)
    embed.add_field(name="負責幹部", value=self.assignee, inline=True)
    embed.add_field(name="當前狀態", value=self.status, inline=False)
    embed.set_footer(text="小貓咪交辦管理系統")
    return embed

  @discord.ui.button(
      label="我要接取 🙋‍♂️",
      style=discord.ButtonStyle.primary,
      custom_id="claim_task_v2",
  )
  async def claim_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if self.assignee != "尚未認領":
      await interaction.response.send_message(
          "⚠️ 這項任務已經有人接走了唷！", ephemeral=True
      )
      return

    self.assignee = interaction.user.mention
    await interaction.message.edit(
        embed=self.update_embed(discord.Color.gold()), view=self
    )
    await interaction.response.send_message(
        f"🎉 成功認領任務：**{self.task_title}**！", ephemeral=True
    )

  @discord.ui.button(
      label="回報完成 ✅",
      style=discord.ButtonStyle.success,
      custom_id="complete_task_v2",
  )
  async def complete_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self.status = f"已完工 ✨ (由 {interaction.user.mention} 確認)"
    completed_embed = self.update_embed(discord.Color.green())

    for child in self.children:
      child.disabled = True

    await interaction.message.edit(embed=completed_embed, view=self)
    await interaction.response.send_message(
        f"🏆 任務【{self.task_title}】已圓滿結案！", ephemeral=False
    )

    archive_channel = self.bot.get_channel(ARCHIVE_CHANNEL_ID)
    if archive_channel:
      archive_embed = discord.Embed(
          title=f"📁 已歸檔交辦事項：{self.task_title}",
          description=self.task_desc,
          color=discord.Color.blue(),
      )
      archive_embed.add_field(
          name="指派人", value=self.creator.mention, inline=True
      )
      archive_embed.add_field(
          name="執行幹部", value=self.assignee, inline=True
      )
      archive_embed.add_field(
          name="結案狀態", value=self.status, inline=False
      )
      archive_embed.set_footer(text="歷史紀錄自動備份")
      await archive_channel.send(embed=archive_embed)


class TaskCog(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  @discord.app_commands.command(
      name="交辦", description="發布一項新的幹部交辦任務卡片"
  )
  @discord.app_commands.describe(title="任務標題", content="任務詳細說明與要求")
  async def create_task(
      self, interaction: discord.Interaction, title: str, content: str
  ):
    view = TaskView(title, content, interaction.user, self.bot)
    embed = view.update_embed(discord.Color.gold())
    await interaction.response.send_message(
        embed=embed, view=view, ephemeral=False
    )


# 💡 就是少這段！Discord 讀取 Cog 時一定要找這個 setup 函式
async def setup(bot):
  await bot.add_cog(TaskCog(bot))
