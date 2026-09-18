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

    # 直接強制載入 profile_shop 模組來追蹤詳細錯誤
    try:
        await bot.load_extension('cogs.profile_shop')
        print('✅ 成功強制載入模組: profile_shop')
    except Exception as e:
        print(f'❌ 載入 profile_shop 失敗，錯誤原因是：{e}')

    # 自動載入 cogs 資料夾底下的其他模組
    if os.path.exists('./cogs'):
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                cog_name = filename[:-3]
                if cog_name == 'profile_shop':
                    continue  # 剛剛已經手動載過了，跳過避免重複
                try:
                    await bot.load_extension(f'cogs.{cog_name}')
                    print(f'已成功載入模組: {cog_name}')
                except Exception as e:
                    print(f'載入模組 {cog_name} 失敗: {e}')

    # 💡 自動抓取機器人所在的所有伺服器，並瞬間同步指令（不用手動改 ID）
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f'已瞬間同步伺服器 [{guild.name}] 的指令，共 {len(synced)} 個')
        except Exception as e:
            print(f'同步伺服器 [{guild.name}] 失敗: {e}')

# 3. 程式進入點
if __name__ == '__main__':
    # 啟動 Flask 背景執行緒
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # 啟動 Discord 機器人
    TOKEN = os.getenv('DISCORD_TOKEN')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print('錯誤：找不到 DISCORD_TOKEN 環境變數！')
