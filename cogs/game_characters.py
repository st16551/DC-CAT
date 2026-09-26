from datetime import datetime, timedelta
import io
import re
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# 引入共用的絕對路徑資料庫連線
from utils.database import DB_FILE, get_db_connection


def update_user_activity(discord_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,)
    )
    cursor.execute(
        "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE discord_id = ?",
        (discord_id,),
    )
    conn.commit()
    conn.close()


# ===================== 請假互動視窗與按鈕 =====================


class LeaveModal(discord.ui.Modal, title="📝 填寫公會請假單"):
    start_date_input = discord.ui.TextInput(
        label="開始日期 (格式: 月/日)",
        placeholder="例如：9/10",
        required=True,
        max_length=20,
    )
    end_date_input = discord.ui.TextInput(
        label="結束日期 (格式: 月/日)",
        placeholder="例如：9/15 (如果當天請完可填同一天)",
        required=True,
        max_length=20,
    )
    reason_input = discord.ui.TextInput(
        label="請假原因",
        placeholder="例如：家裡有事、期末考、加班等...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_date = self.start_date_input.value.strip()
            end_date = self.end_date_input.value.strip()

            # 日期格式驗證邏輯
            date_pattern = re.compile(
                r"^([1-9]|1[0-2])/([1-9]|[1-2][0-9]|3[0-1])$"
            )

            if not date_pattern.match(start_date) or not date_pattern.match(
                end_date
            ):
                await interaction.response.send_message(
                    "❌ **日期格式錯誤！** 請確實填寫類似 `9/10` 或 `09/15` 的有效日期格式，請勿填寫無效數字。",
                    ephemeral=True,
                )
                return

            discord_id = interaction.user.id
            reason = self.reason_input.value

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO users (discord_id) VALUES (?)",
                (discord_id,),
            )
            cursor.execute(
                "INSERT INTO leaves (discord_id, reason, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)",
                (discord_id, reason, start_date, end_date, "審核中"),
            )
            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="📄 【新請假申請待審核】", color=discord.Color.orange()
            )
            embed.add_field(
                name="請假成員", value=interaction.user.mention, inline=False
            )
            embed.add_field(
                name="請假區間",
                value=f"`{start_date}` ~ `{end_date}`",
                inline=False,
            )
            embed.add_field(name="請假原因", value=reason, inline=False)
            embed.set_footer(text=f"申請人 ID: {discord_id}")

            view = LeaveReviewView()

            await interaction.response.send_message(
                content=f"✅ **{interaction.user.mention} 你的請假單已送出，已轉交管理員審核！**",
                ephemeral=True,
            )

            guild = interaction.guild
            review_channel = discord.utils.get(
                guild.text_channels, name="🔒│請假審核專區"
            )

            if not review_channel:
                review_channel = discord.utils.find(
                    lambda c: "請假審核" in c.name, guild.text_channels
                )

            if not review_channel:
                target_channel_name = "🔒│請假審核專區"
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=False
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        embed_links=True,
                    ),
                }
                for role in guild.roles:
                    if role.permissions.administrator:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True, send_messages=True
                        )

                try:
                    review_channel = await guild.create_text_channel(
                        target_channel_name, overwrites=overwrites
                    )
                except Exception as e_create:
                    print(f"⚠️ [請假系統] 自動建立審核頻道失敗: {e_create}")
                    review_channel = interaction.channel

            if review_channel:
                try:
                    await review_channel.send(embed=embed, view=view)
                except Exception as e_send:
                    print(f"⚠️ [請假系統] 傳送至審核頻道失敗: {e_send}")
                    await interaction.channel.send(embed=embed, view=view)
            else:
                await interaction.channel.send(embed=embed, view=view)

        except Exception as e:
            import traceback

            print("================ 嚴重的請假 Modal 崩潰錯誤 ================")
            traceback.print_exc()
            print("=========================================================")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ 系統發生預期外的錯誤，已記錄至後台。錯誤代碼: `{e}`",
                        ephemeral=True,
                    )
            except Exception:
                pass


# 📌 常駐型請假按鈕面板（點擊後開啟 Modal）
class PersistentLeaveButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 永久常駐

    @discord.ui.button(
        label="📝 點此填寫請假單",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_leave_modal_btn",
    )
    async def open_leave_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(LeaveModal())


class LeaveReviewView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ 批准請假",
        style=discord.ButtonStyle.success,
        custom_id="leave_approve_btn_v5",
    )
    async def approve_leave(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 只有管理員可以審核請假！", ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "✅ 【請假已批准】"
        embed.add_field(
            name="審核者", value=interaction.user.mention, inline=False
        )

        target_discord_id = int(embed.footer.text.split("ID: ")[-1])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE leaves SET status = '已批准' WHERE discord_id = ?",
            (target_discord_id,),
        )
        conn.commit()
        conn.close()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"✅ 已經批准了該位成員的請假申請。", ephemeral=True
        )

    @discord.ui.button(
        label="❌ 駁回申請",
        style=discord.ButtonStyle.danger,
        custom_id="leave_reject_btn_v5",
    )
    async def reject_leave(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 只有管理員可以審核請假！", ephemeral=True
            )
            return

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "❌ 【請假已駁回】"
        embed.add_field(
            name="審核者", value=interaction.user.mention, inline=False
        )

        target_discord_id = int(embed.footer.text.split("ID: ")[-1])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE leaves SET status = '已駁回' WHERE discord_id = ?",
            (target_discord_id,),
        )
        conn.commit()
        conn.close()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        guild = interaction.guild
        target_member = guild.get_member(target_discord_id)

        notify_text = f"❌ **{interaction.user.mention} 已經駁回了您的請假申請。**"
        if target_member:
            try:
                await target_member.send(notify_text)
            except Exception:
                pass
            await interaction.followup.send(
                f"❌ 已經駁回了該位成員的請假申請，並已嘗試私訊通知 {target_member.mention}。",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ 已經駁回了該位成員的請假申請。", ephemeral=True
            )


class LeaveCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(PersistentLeaveButtonView())
        self.bot.add_view(LeaveReviewView())

    @app_commands.command(
        name="請假", description="填寫並送出您的公會請假單"
    )
    async def request_leave(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LeaveModal())

    @app_commands.command(
        name="架設請假面板", description="在當前頻道發送常駐請假按鈕面板"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_leave_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏖️ 公會請假系統",
            description=(
                "如果需要請假，請點擊下方按鈕填寫請假單。\n送出後將由管理員進行審核，請耐心等候！"
            ),
            color=discord.Color.blue(),
        )
        view = PersistentLeaveButtonView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            "✅ 已成功在此頻道架設常駐請假面板！", ephemeral=True
        )

    # 📌 管理員專用：下載包含請假時間的完整試算表報表
    @app_commands.command(
        name="下載請假報表", description="【管理員專用】下載包含 Discord 資訊與請假時間的試算表檔案"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def download_leave_report(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 抓取使用者基本資料，並透過 LEFT JOIN 取得其最新的請假區間（可根據你的資料庫表格調整欄位名稱）
        # 假設你的使用者資料表叫 users，內含 discord_id, game_name, profession, sub_guild, joined_at 等欄位
        try:
            cursor.execute("""
                u.discord_id, u.discord_name, u.game_name, u.profession, u.sub_guild, u.joined_at,
                l.start_date, l.end_date
                FROM users u
                LEFT JOIN leaves l ON u.discord_id = l.discord_id AND l.status = '已批准'
            """)
            rows = cursor.fetchall()
        except Exception:
            # 如果資料庫結構不同，退回單純抓取 leaves 與對應的使用者資訊
            cursor.execute("""
                SELECT u.discord_id, l.start_date, l.end_date 
                FROM users u 
                LEFT JOIN leaves l ON u.discord_id = l.discord_id
            """)
            rows = cursor.fetchall()
            
        conn.close()

        # 建立 CSV 檔案內容（使用 utf-8-sig 讓 Excel 能夠正確讀取中文）
        csv_output = io.StringIO()
        # 寫入對應你截圖的表頭，最後面多加「請假時間」
        csv_output.write("Discord ID,Discord 帳號,遊戲角色 ID,職業,分配分會,入會時間,請假時間\n")

        for row in rows:
            # 兼容不同的欄位長度防呆
            discord_id = row[0] if len(row) > 0 else ""
            
            # 試著從 Discord 伺服器取得即時的帳號名稱
            member = interaction.guild.get_member(discord_id)
            discord_name = member.name if member else str(discord_id)
            
            game_name = row[2] if len(row) > 2 and row[2] else "-"
            profession = row[3] if len(row) > 3 and row[3] else "-"
            sub_guild = row[4] if len(row) > 4 and row[4] else "-"
            joined_at = row[5] if len(row) > 5 and row[5] else "-"
            
            start_date = row[6] if len(row) > 6 and row[6] else ""
            end_date = row[7] if len(row) > 7 and row[7] else ""
            
            # 組合請假時間格式 (例如 7/10~7/30)，若無請假則空白
            leave_time_str = f"{start_date}~{end_date}" if start_date and end_date else ""

            csv_output.write(f'"{discord_id}","{discord_name}","{game_name}","{profession}","{sub_guild}","{joined_at}","{leave_time_str}"\n')

        # 轉換成二進位檔案串流準備上傳
        file_bytes = io.BytesIO(csv_output.getvalue().encode("utf-8-sig"))
        file_bytes.seek(0)
        
        discord_file = discord.File(file_bytes, filename="guild_leave_report.csv")
        await interaction.followup.send(
            "✅ **以下是為你產生的公會與請假試算表報表：**\n你可以直接下載此 `.csv` 檔案並用 Excel 或 Google 試算表開啟。",
            file=discord_file,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(LeaveCog(bot))
