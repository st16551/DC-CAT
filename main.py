@bot.event
async def on_ready():
    print(f"========================================")
    print(f" 機器人已成功登入：{bot.user.name} (ID: {bot.user.id})")
    print(f"========================================")

    # 1. 確保資料庫表格完整建立
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

    # 4. ⚡ 改為指定伺服器同步（秒級生效，並強制快取成員）
    GUILD_ID = 1341056514282229841  # 例如：123456789012345678
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f" 🌐 已針對伺服器同步 {len(synced)} 個 Slash 互動指令。")
    except Exception as e:
        print(f" ❌ 指令同步失敗: {e}")

    print(f"========================================")
    print(f" 🚀 DC-CAT 系統全面啟動完成，開始守護公會！")
    print(f"========================================")
