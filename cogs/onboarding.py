import sqlite3
import discord
from discord import app_commands
from discord.ext import commands  # <--- 已補上這行
import gspread
from google.oauth2.service_account import Credentials

# --- 4. 幹部管理與指令 Cog ---
class GuildAdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="架設面試面板",
        description="【管理員】在當前頻道發送常駐的公會規則與入會申請面板",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_panel(self, interaction: discord.Interaction):
        # 1. 搶先延遲回應，防止 3 秒超時報 10062 Unknown interaction 錯誤
        await interaction.response.defer(ephemeral=True)

        rules_text = (
            "歡迎大家加入 **Escalation**，希望這裡不只是一起遊玩的公會，也是一個能互相幫助、輕鬆交流的地方。為了維持良好的公會環境，請所有成員共同遵守以下規則：\n\n"
            "一、請尊重每位成員，禁止辱罵、嘲諷、挑釁、人身攻擊、歧視或氣氛 刻意引起爭吵。\n"
            "（視情節幹部調解後討論懲處）\n\n"
            "二、遊戲中若發生意見不合，請先冷靜溝通，不要在公會頻道互嗆、洗頻或影響其他成員。\n"
            "（視情節幹部調解後討論懲處）\n\n"
            "三、禁止詐騙、惡意搶奪資源、欺騙交易、借用裝備或金錢後不歸還等行為。\n\n"
            "四、公會活動請盡量配合參加。\n\n"
            "五、分配裝備、獎勵或資源時，請尊重幹部及活動負責人的安排，不得因未取得物品而鬧事或惡意退團。\n\n"
            "六、禁止在公會內大量發布廣告、外掛、代儲、買賣帳號、不明連結或其他可能造成成員損失的內容。\n\n"
            "七、請勿隨意洩漏其他成員的私人資料、對話紀錄、照片或公會內部資訊。\n"
            "（違者踢出）\n\n"
            "八、五天未上線者，如沒有提前告知，可能會視公會人數狀況進行整理；回歸後仍可再次申請加入。\n\n"
            "九、若遇到糾紛或不確定如何處理，請私下聯絡會長或幹部，避免公開爭吵。\n\n"
            "十、嚴重違反規則、屢勸不聽或影響公會氣氛者，將依情況給予提醒、警告、停權或移出公會。\n\n"
            "**Escalation** 歡迎每一位真心想一起遊玩、互相幫助的成員。實力強弱不是最重要的，基本的尊重、誠信與團隊精神才是公會能夠長久走下去的原因。\n\n"
            "希望大家共同維護 **Escalation** 的氣氛，玩得開心，也讓每一位加入的人都能感受到歸屬感。\n\n"
            "老話一句這裡是家，我們不是敵人而是你們的避風港。"
        )

        embed = discord.Embed(
            title="📜 Escalation 公會規則與入會申請",
            description=rules_text,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="👇 請詳細閱讀上方規則後，點擊下方按鈕打勾同意並填寫入會資料！")

        await interaction.channel.send(embed=embed, view=RulesAcceptanceView())
        
        # 2. 透過 followup 發送隱藏成功提示
        await interaction.followup.send("✅ 面試面板已發布！", ephemeral=True)

    @app_commands.command(
        name="同步試算表id",
        description="【管理員】從 Google 試算表同步資料：自動補齊 A 欄 ID，並同步所有成員資料至本地資料庫",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_spreadsheet_ids(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            client = get_gspread_client()
            sheet = client.open_by_key(SPREADSHEET_ID).sheet1
            
            rows = sheet.get_all_values()
            if not rows or len(rows) <= 1:
                await interaction.followup.send("❌ 試算表目前沒有足夠的資料！", ephemeral=True)
                return
            
            guild = interaction.guild
            updated_id_count = 0
            db_sync_count = 0
            not_found_list = []
            
            cell_updates = []
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            for index, row in enumerate(rows[1:], start=2):
                discord_id_cell = row[0].strip() if len(row) > 0 else ""
                discord_name_cell = row[1].strip() if len(row) > 1 else ""
                char_name_val = row[2].strip() if len(row) > 2 else ""
                class_val = row[3].strip() if len(row) > 3 else ""
                branch_val = row[4].strip() if len(row) > 4 else "未分配"
                game_name_val = "靈谷"
                
                target_discord_id = None
                
                if not discord_id_cell and discord_name_cell:
                    member = discord.utils.get(guild.members, name=discord_name_cell)
                    if not member:
                        member = discord.utils.get(guild.members, display_name=discord_name_cell)
                    
                    if member:
                        target_discord_id = member.id
                        cell_updates.append(gspread.Cell(row=index, col=1, value=str(target_discord_id)))
                        updated_id_count += 1
                    else:
                        not_found_list.append(discord_name_cell)
                elif discord_id_cell.isdigit():
                    target_discord_id = int(discord_id_cell)
                
                if target_discord_id and char_name_val:
                    cursor.execute("""
                        INSERT INTO game_characters (discord_id, discord_name, game_name, character_name, main_class, branch)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(discord_id) DO UPDATE SET
                            discord_name = excluded.discord_name,
                            game_name = excluded.game_name,
                            character_name = excluded.character_name,
                            main_class = excluded.main_class,
                            branch = excluded.branch
                    """, (target_discord_id, discord_name_cell, game_name_val, char_name_val, class_val, branch_val))
                    db_sync_count += 1

            if cell_updates:
                sheet.update_cells(cell_updates)

            conn.commit()
            conn.close()
            
            msg = f"✅ **同步完成！**\n"
            msg += f"• 自動補齊試算表 A 欄 ID：`{updated_id_count}` 筆\n"
            msg += f"• 同步更新至本地資料庫：`{db_sync_count}` 筆資料\n"
            
            if not_found_list:
                msg += f"\n⚠️ 以下帳號在伺服器中找不到對應成員：\n`{', '.join(not_found_list)}`"
            
            await interaction.followup.send(msg, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 同步過程發生錯誤：`{e}`", ephemeral=True)
