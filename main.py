# ==================================================
# 檔案名稱：main.py
# 檔案用途：DC-CAT 機器人核心啟動與模組自動加載器（含 Render 不休眠服務與防錯機制）
# ==================================================

import asyncio
import os
import traceback
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# 啟動 Flask 保持 Render 雲端不休眠
app = Flask("")

@app.route("/")
def home():
    return "DC-CAT is running and active!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# 初始化機器人設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"========================================")
    print(f" 機器人已成功登入：{bot.user.name} (ID: {bot.user.id})")
    print(f"========================================")

    # 確保 cogs 資料夾存在
    if not os.path.exists("./cogs"):
        os.makedirs("./cogs")
        print(" 📁 已自動建立 ./cogs 資料夾")

    # 自動載入 cogs 資料夾底下的所有模組
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f"cogs.{cog_name}")
                print(f" [模組載入成功] cogs.{cog_name}")
            except Exception as e:
                print(f" ❌ [模組載入失敗] cogs.{cog_name}: {e}")
                traceback.print_exc()

    # 同步 Slash (App Commands) 指令到 Discord
    try:
        synced = await bot.tree.sync()
        print(f" 🌐 已同步 {len(synced)} 個 Slash 互動指令。")
    except Exception as e:
        print(f" ❌ 指令同步失敗: {e}")

    print(f"========================================")
    print(f" 🚀 DC-CAT 系統全面啟動完成，開始守護公會！")
    print(f"========================================")


# 主程式進入點
if __name__ == "__main__":
    keep_alive()  # 啟動網頁心跳
    TOKEN = os.getenv("DISCORD_TOKEN")  # 從 Render 環境變數讀取 Token
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ 錯誤：找不到 DISCORD_TOKEN 環境變數！請確認是否已在 Render 設定密鑰。")
