import gspread
import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_db_connection, init_db as init_core_db
from utils.sheets import get_member_sheet

MEMBER_ROLE_NAME = "成員"
FORUM_CHANNEL_ID = 1549273328705872002
AUDIT_CHANNEL_ID = 1549263078892249108

ROLE_IDS = {
    "成員": 1527550855631339601,
    "牧師": 1529725865024557196,
    "聖騎": 1529726272471568454,
    "聖騎士": 1529726272471568454,
    "槍手": 1529726360568987708,
    "死靈": 1529726490734886922,
    "法師": 1529726652341420113,
    "忍者": 1529726861570216083,
    "編織": 1529727042516422798,
    "戰士": 1529734718193668127,
    "1會": 1541087729088200765,
    "2会": 1541087803151098079,
    "2會": 1541087803151098079,
    "3会": 1541087848298446998,
    "3會": 1541087848298446998,
}

init_core_db()


# --- 1. 遊戲資料填寫表單 (Modal) ---
class CharacterModal(discord.ui.Modal, title="Escalation - 成員入會申請登記"):
    def __init__(self, selected_class: str):
        super().__init__()
        self.selected_class_value = selected_class

    character_name = discord.ui.TextInput(
        label="遊戲內 ID / 角色名稱",
        placeholder="請輸入你的遊戲角色名稱",
        max_length=50,
        required=True,
    )
    nickname = discord.ui.TextInput(
        label="希望我們叫的暱稱",
        placeholder="例如：高須鼠兒",
        max_length=30,
        required=True,
    )
    experience = discord.ui.TextInput(
        label="體驗內容與自我介紹（請在下方填寫答案）",
        style=discord.TextStyle.paragraph,
        default=(
            "1. 前一個公會：\n"
            "2. 想體驗 pvp 還是 pve：\n"
            "3. 有沒有朋友或推薦人在公會：\n"
            "4. 怎麼會想加入我們："
        ),
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        role = discord.utils.get(interaction.guild.roles, name=MEMBER_ROLE_NAME)
        if role and role in interaction.user.roles:
            await interaction.response.send_message("❌ 你已經擁有公會成員身分組，無法重複送出申請！", ephemeral=True)
            return

        main_class = self.selected_class_value
        game_name_val = "靈谷"

        embed = discord.Embed(
            title="📝 申請已送出，等待幹部審核",
            description=(
                "您的入會申請已經成功送出！\n• 系統已收到您的資料（包含您所選的職業），請靜候幹部審核。\n•"
                " 幹部審核並指定分會後將自動發放對應身分組。"
            ),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        audit_channel = interaction.guild.get_channel(AUDIT_CHANNEL_ID)
        if audit_channel:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT branch, main_class, COUNT(*) FROM game_characters WHERE branch IN ('1會', '2會', '3會') GROUP BY branch, main_class")
            rows = cursor.fetchall()
            
            cursor.execute("SELECT branch, COUNT(*) FROM game_characters WHERE branch IN ('1會', '2會', '3會') GROUP BY branch")
            branch_totals = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()

            stats_text_list = []
            for b in ["1會", "2會", "3會"]:
                total = branch_totals.get(b, 0)
                b_rows = [r for r in rows if r[0] == b]
                class_summary = ", ".join([f"{c[1]}:{c[2]}" for c in b_rows]) if b_rows else "目前無成員"
                stats_text_list.append(f"🏰 **{b}** (總計: {total}人)\n└ 職業: {class_summary}")

            audit_embed = discord.Embed(
                title="🚨 收到新的入會申請",
                description="\n".join(stats_text_list),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            audit_embed.add_field(
                name="申請人 (Discord)",
                value=f"{interaction.user.mention} (`{interaction.user.name}`)",
                inline=False,
            )
            audit_embed.add_field(
                name="遊戲 ID", value=self.character_name.value, inline=True
            )
            audit_embed.add_field(
                name="🛡️ 填寫職業",
                value=f"**`{main_class}`**",
                inline=True,
            )
            audit_embed.add_field(
                name="希望暱稱", value=self.nickname.value, inline=True
            )
            audit_embed.add_field(
                name="詳細資料與問答",
                value=self.experience.value,
                inline=False,
            )
            audit_embed.set_footer(text=f"Discord ID: {interaction.user.id} | 請在下方選擇分會並通過審核")

            view = InterviewAuditView(
                applicant_id=interaction.user.id,
                discord_name=str(interaction.user),
                game_name=game_name_val,
                character_name=self.character_name.value,
                main_class=main_class,
                nickname=self.nickname.value,
                extra_info=self.experience.value,
            )
            await audit_channel.send(embed=audit_embed, view=view)


# --- 1.1 職業下拉選單介面 ---
class ClassSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        placeholder="👉 點此展開並選擇您的職業（防止打錯字）",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="聖騎"),
            discord.SelectOption(label="戰士"),
            discord.SelectOption(label="法師"),
            discord.SelectOption(label="死靈"),
            discord.SelectOption(label="牧師"),
            discord.SelectOption(label="槍手"),
            discord.SelectOption(label="忍者"),
            discord.SelectOption(label="編織"),
        ],
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        role = discord.utils.get(interaction.guild.roles, name=MEMBER_ROLE_NAME)
        if role and role in interaction.user.roles:
            await interaction.response.send_message(
                "❌ 你已經擁有公會身分組，不需要重複填寫申請！",
                ephemeral=True
            )
            return

        chosen_class = select.values[0]
        modal = CharacterModal(selected_class=chosen_class)
        await interaction.response.send_modal(modal)


# --- 2. 幹部審核專用介面 ---
class InterviewAuditView(discord.ui.View):
    def __init__(
        self,
        applicant_id: int = 0,
        discord_name: str = "",
        game_name: str = "靈谷",
        character_name: str = "",
        main_class: str = "聖騎",
        nickname: str = "",
        extra_info: str = "",
    ):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.discord_name = discord_name
        self.game_name = game_name
        self.character_name = character_name
        self.main_class = main_class
        self.nickname = nickname
        self.extra_info = extra_info
        self.selected_branch = "1會"

    @discord.ui.select(
        placeholder="🏰 點此選擇要分配的分會（預設：1會）",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="1會", description="分配至第一分會"),
            discord.SelectOption(label="2會", description="分配至第二分會"),
            discord.SelectOption(label="3會", description="分配至第三分會"),
        ],
        custom_id="audit_branch_select"
    )
    async def branch_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_branch = select.values[0]
        await interaction.response.send_message(f"📌 已將目標分會暫定為：**{self.selected_branch}**，請點擊下方按鈕確認通過。", ephemeral=True)

    @discord.ui.button(
        label="✅ 通過審核並發放身分組",
        style=discord.ButtonStyle.green,
        custom_id="audit_approve_btn",
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        
        app_id = self.applicant_id
        if app_id == 0 and interaction.message.embeds:
            footer_text = interaction.message.embeds[0].footer.text
            if footer_text and "Discord ID:" in footer_text:
                try:
                    app_id = int(footer_text.split("Discord ID:")[1].split("|")[0].strip())
                except Exception:
                    pass

        applicant = guild.get_member(app_id) if app_id != 0 else None
        target_branch = self.selected_branch

        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            fields = {f.name: f.value for f in embed.fields}
            if not self.character_name:
                self.character_name = fields.get("遊戲 ID", "").replace("`", "").strip()
            if not self.main_class or self.main_class == "聖騎":
                filled = fields.get("🛡️ 填寫職業") or fields.get("填寫職業") or ""
                cleaned = filled.replace("*", "").replace("`", "").strip()
                if cleaned:
                    self.main_class = cleaned
            if not self.nickname:
                self.nickname = fields.get("希望暱稱", "").strip()
            if not self.extra_info:
                self.extra_info = fields.get("詳細資料與問答", "")
            if not self.discord_name:
                self.discord_name = fields.get("申請人 (Discord)", "")

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT OR IGNORE INTO game_characters (discord_id) VALUES (?)",
            (app_id,),
        )
        cursor.execute(
            """
            UPDATE game_characters 
            SET discord_name = ?, game_name = ?, character_name = ?, main_class = ?, branch = ?
            WHERE discord_id = ?
        """,
            (
                self.discord_name,
                self.game_name,
                self.character_name,
                self.main_class,
                target_branch,
                app_id,
            ),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO game_characters (discord_id, discord_name, game_name, character_name, main_class, branch)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    app_id,
                    self.discord_name,
                    self.game_name,
                    self.character_name,
                    self.main_class,
                    target_branch,
                ),
            )
        conn.commit()
        conn.close()

        try:
            sheet = get_member_sheet()
            current_time = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([
                str(app_id),
                self.discord_name,
                self.character_name,
                self.main_class,
                target_branch,
                current_time
            ])
        except Exception as e:
            print(f"❌ 寫入 Google 試算表失敗：{e}")

        if applicant:
            roles_to_add = []
            member_role_id = ROLE_IDS.get("成員")
            if member_role_id:
                member_role = guild.get_role(member_role_id)
                if member_role:
                    roles_to_add.append(member_role)
                
            class_role_id = ROLE_IDS.get(self.main_class)
            if class_role_id:
                class_role = guild.get_role(class_role_id)
                if class_role:
                    roles_to_add.append(class_role)
                
            branch_role_id = ROLE_IDS.get(target_branch)
            if branch_role_id:
                branch_role = guild.get_role(branch_role_id)
                if branch_role:
                    roles_to_add.append(branch_role)

            try:
                if roles_to_add:
                    await applicant.add_roles(*roles_to_add)
            except Exception as e:
                print(f"❌ 發放身分組失敗：{e}")

        forum_channel = guild.get_channel(FORUM_CHANNEL_ID)
        if forum_channel and isinstance(forum_channel, discord.ForumChannel):
            post_content = (
                f"🎉 **歡迎新成員加入 Escalation！**\n\n"
                f"• **Discord 帳號**：`{self.discord_name}`\n"
                f"• **遊戲 ID**：`{self.character_name}`\n"
                f"• **暱稱**：`{self.nickname}`\n"
                f"• **職業**：`{self.main_class}`\n"
                f"• **指定分會**：`{target_branch}`\n\n"
                f"**詳細資訊與自我介紹：**\n{self.extra_info}\n\n"
                f"感謝各位夥伴，請大家多多指教！"
            )
            await forum_channel.create_thread(
                name=f"【{target_branch}】{self.character_name} ({self.main_class})",
                content=post_content,
            )

        await interaction.response.edit_message(
            content=(
                f"✅ 已由 {interaction.user.mention} 審核**通過**！\n•"
                f" 玩家填寫職業：`{self.main_class}`\n•"
                f" 幹部指定分會：**{target_branch}**\n•"
                f" 🎯 **已自動發放 成員、職業、分會身分組！**\n•"
                f" 📁 **已同步寫入 Google 試算表！**"
            ),
            view=None,
        )

    @discord.ui.button(
        label="❌ 拒絕申請",
        style=discord.ButtonStyle.red,
        custom_id="audit_reject_btn",
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"❌ 已由 {interaction.user.mention} 審核**拒絕**該申請。",
            view=None,
        )


# --- 3. 規章確認與點擊介面 ---
class RulesAcceptanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ 我已閱讀並同意公會規則，開始填寫申請",
        style=discord.ButtonStyle.blurple,
        custom_id="rules_accept_button",
    )
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name=MEMBER_ROLE_NAME)
        if role and role in interaction.user.roles:
            await interaction.response.send_message(
                "❌ 你已經擁有公會身分組，不需要重複填寫申請！",
                ephemeral=True
            )
            return

        view = ClassSelectView()
        await interaction.response.send_message(
            "請先點擊下方選單選擇您的職業：",
            view=view,
            ephemeral=True,
        )


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
        await interaction.response.send_message("✅ 面試面板已發布！", ephemeral=True)

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

    @app_commands.command(
        name="同步試算表id",
        description="【管理員】從 Google 試算表同步資料：自動補齊 A 欄 ID，並同步所有成員資料至本地資料庫",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_spreadsheet_ids(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            sheet = get_member_sheet()
            
            rows = sheet.get_all_values()
            if not rows or len(rows) <= 1:
                await interaction.followup.send("❌ 試算表目前沒有足夠的資料！", ephemeral=True)
                return
            
            guild = interaction.guild
            updated_id_count = 0
            db_sync_count = 0
            not_found_list = []
            
            cell_updates = []
            
            conn = get_db_connection()
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


async def setup(bot):
    bot.add_view(RulesAcceptanceView())
    bot.add_view(InterviewAuditView())
    await bot.add_cog(GuildAdminCog(bot))
