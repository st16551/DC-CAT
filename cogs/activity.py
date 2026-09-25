from datetime import datetime
import io
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

DB_FILE = "guild_database.db"

# 暫存語音進入時間 (discord_id: datetime)
voice_sessions = {}


def init_activity_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            voice_seconds INTEGER DEFAULT 0,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()
    conn.close()


init_activity_db()


class ActivityCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # 💬 監聽文字訊息：自動累計發言數與最後活躍時間
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        discord_id = message.author.id
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,)
        )
        cursor.execute(
            """
            UPDATE users 
            SET message_count = message_count + 1, last_active = ? 
            WHERE discord_id = ?
        """,
            (now_str, discord_id),
        )
        conn.commit()
        conn.close()

    # 🎙️ 監聽語音狀態：精準計算進入與離開的語音總秒數
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        discord_id = member.id
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (discord_id) VALUES (?)", (discord_id,)
        )

        # 進入語音
        if before.channel is None and after.channel is not None:
            voice_sessions[discord_id] = now

        # 離開語音
        elif before.channel is not None and after.channel is None:
            if discord_id in voice_sessions:
                start_time = voice_sessions.pop(discord_id)
                duration = int((now - start_time).total_seconds())
                if duration > 0:
                    cursor.execute(
                        """
                        UPDATE users 
                        SET voice_seconds = voice_seconds + ?, last_active = ? 
                        WHERE discord_id = ?
                    """,
                        (duration, now_str, discord_id),
                    )
        conn.commit()
        conn.close()

    # 🏆 活躍排行榜指令（高語音權重公式）
    @app_commands.command(
        name="活躍排行", description="查看公會成員的文字與語音活躍排行榜"
    )
    async def show_leaderboard(self, interaction: discord.Interaction):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT discord_id, message_count, voice_seconds, last_active 
            FROM users 
            ORDER BY (message_count + ((voice_seconds / 60.0) * 3)) DESC 
            LIMIT 10
        """
        )
        rows = cursor.fetchall()
        conn.close()

        embed = discord.Embed(
            title="🏆 公會成員活躍排行榜 (語音高權重)", color=discord.Color.gold()
        )

        if not rows:
            embed.description = "目前尚無任何活躍紀錄。"
        else:
            desc = ""
            for idx, (uid, msg_count, voice_sec, last_act) in enumerate(
                rows, 1
            ):
                member = interaction.guild.get_member(uid)
                name = member.display_name if member else f"未知用戶({uid})"
                voice_hours = round(voice_sec / 3600, 1)
                desc += f"**#{idx}** {name}\n 💬 發言: `{msg_count}` 則 | 🎙️ 語音: `{voice_hours}` 小時\n\n"
            embed.description = desc

        await interaction.response.send_message(embed=embed, ephemeral=False)

    # 📁 一鍵導出完整詳細活躍名單 (TXT)
    @app_commands.command(
        name="導出活躍明細",
        description="【管理員】導出包含所有成員文字、語音、最後活躍時間的詳細 TXT 報表",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def export_activity_details(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT discord_id, message_count, voice_seconds, last_active 
            FROM users 
            ORDER BY (message_count + ((voice_seconds / 60.0) * 3)) DESC
        """
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.followup.send(
                "❌ 目前資料庫中沒有任何活躍紀錄可供導出。", ephemeral=True
            )
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_lines = [
            f"=== {interaction.guild.name} 全體成員活躍明細報表 ===",
            f"導出時間：{now_str}",
            f"總計紀錄人數：{len(rows)} 人",
            "=" * 65,
            f"{'成員名稱 (Discord ID)':<30} | {'發言則數':<8} | {'語音時數':<10} | {'最後活躍時間':<20}",
            "-" * 65,
        ]

        for discord_id, msg_count, voice_sec, last_active in rows:
            member = interaction.guild.get_member(discord_id)
            name = (
                f"{member.display_name} ({discord_id})"
                if member
                else f"離線成員 ({discord_id})"
            )
            v_hours = round(voice_sec / 3600, 2)
            last_act_str = last_active if last_active else "從未互動"
            report_lines.append(
                f"{name:<30} | {msg_count:<8} | {v_hours}小時      | {last_act_str:<20}"
            )

        file_content = "\n".join(report_lines)
        file = discord.File(
            fp=io.BytesIO(file_content.encode("utf-8-sig")),
            filename=f"guild_activity_report_{datetime.now().strftime('%Y%m%d')}.txt",
        )

        await interaction.followup.send(
            "📁 **活躍詳細明細導出成功！** 請見下方檔案：", file=file, ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ActivityCog(bot))
