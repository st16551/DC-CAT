import os
from threading import Thread
import discord
from discord.ext import commands
from flask import Flask

# 1. 建立 Flask 伺服器（防止 Render 休眠）
app = Flask('')


@app.route('/')
def home():
  return 'DC-CAT Bot is online and running!'


def run_flask():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


# 2. 設定 Discord 機器人
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
  print(f'目前登入身分 --> {bot.user}')

  # 自動載入 cogs 資料夾底下的所有模組
  if os.path.exists('./cogs'):
    for filename in os.listdir('./cogs'):
      if filename.endswith('.py'):
        cog_name = filename[:-3]
        try:
          await bot.load_extension(f'cogs.{cog_name}')
          print(f'已成功載入模組: {cog_name}')
        except Exception as e:
          print(f'載入模組 {cog_name} 失敗: {e}')

  # 💡【最關鍵】在這裡加上這段，強迫把指令同步給 Discord！
  try:
    synced = await bot.tree.sync()
    print(f'已成功同步 {len(synced)} 個應用程式指令！')
  except Exception as e:
    print(f'同步指令失敗: {e}')


# 3. 程式進入點
if __name__ == '__main__':
  flask_thread = Thread(target=run_flask)
  flask_thread.start()

  TOKEN = os.getenv('DISCORD_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('錯誤：找不到 DISCORD_TOKEN 環境變數！')
