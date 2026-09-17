import discord
from discord.ext import commands


class Example(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  @commands.command(name='ping')
  async def ping(self, ctx):
    """測試機器人是否正常運作"""
    latency = round(self.bot.latency * 1000)
    await ctx.send(f'pong! 機器人延遲時間: {latency}ms')


async def setup(bot):
  await bot.add_cog(Example(bot))