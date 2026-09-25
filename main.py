# ==================================================
# 檔案名稱：main.py
# 檔案用途：DC-CAT 機器人核心啟動與模組自動加載器（整合完整 Flask 網頁儀表板）
# ==================================================

import asyncio
import os
import traceback
import discord
from discord.ext import commands
from threading import Thread

# 🛡️ 引入資料庫初始化，確保啟動時自動建立所有表格（解決 active_debuffs 報錯）
from utils.database import init_db

# 引入你在根目錄寫好的完整網頁儀表板 app.py
from app import app

def run_flask():
    # 讓 Flask 在背景執行，連接 Render 指定的連接埠
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

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

    # 1. 確保資料庫表格完整建立（自動修復 missing table 錯誤）
    try:
        init_db()
        print(" 🗄️ 資料庫表格檢查與初始化完成")
    except Exception as e:
        print(f" ❌ 資料庫初始化失敗: {e}")

    # 2. 確保 cogs 資料夾存在
    if not os.path.exists("./cogs"):
        os.makedirs("./cogs")
        print(" 📁 已自動建立 ./cogs 資料夾")

    # 3. 自動載入 cogs 資料夾底下的所有模組
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f"cogs.{cog_name}")
                print(f" [模組載入成功] cogs.{cog_name}")
            except Exception as e:
                print(f" ❌ [模組載入失敗] cogs.{cog_name}: {e}")
                traceback.print_exc()

    # 4. 同步 Slash (App Commands) 指令到 Discord
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
    keep_alive()  # 啟動完整網頁儀表板心跳
    TOKEN = os.getenv("DISCORD_TOKEN")  # 從 Render 環境變數讀取 Token
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ 錯誤：找不到 DISCORD_TOKEN 環境變數！請確認是否已在 Render 設定密鑰。")
