# ==================================================
# 檔案名稱：cogs/activity_stats.py
# 檔案用途：個人活躍統計（相容 utils.DATA_FILE 與 SQLite）
# ==================================================

import json
import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils import DATA_FILE, activity_data, load_data
from utils.database import get_db_connection


def _read_json_store():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    fallback = load_data()
    return fallback if isinstance(fallback, dict) else {}


class ActivityStatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _collect_stats(self, discord_id: int) -> dict:
        uid = str(discord_id)
        stats = {
            "message_count": 0,
            "voice_seconds": 0,
            "voice_hours": 0.0,
            "last_active": "從未記錄",
            "level": 1,
            "su_coins": 0,
        }

        json_store = _read_json_store()
        json_activity = json_store.get("activity_data") or activity_data or {}
        if isinstance(json_activity, dict) and uid in json_activity:
            entry = json_activity[uid] or {}
            stats["message_count"] = int(entry.get("message_count") or 0)
            stats["voice_seconds"] = int(entry.get("voice_seconds") or 0)
            stats["last_active"] = entry.get("last_active") or stats["last_active"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.message_count, u.voice_seconds, u.last_active,
                   m.voice_hours, m.level, m.su_coins, m.messages_count
            FROM users u
            LEFT JOIN member_levels m ON u.discord_id = m.discord_id
            WHERE u.discord_id = ?
            """,
            (discord_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                """
                SELECT level, su_coins, messages_count, voice_hours
                FROM member_levels WHERE discord_id = ?
                """,
                (discord_id,),
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                stats["level"] = row["level"] or 1
                stats["su_coins"] = row["su_coins"] or 0
                stats["message_count"] = max(stats["message_count"], row["messages_count"] or 0)
                stats["voice_hours"] = float(row["voice_hours"] or 0)
            return stats
        conn.close()

        db_messages = row["message_count"] if row["message_count"] is not None else 0
        extra_messages = row["messages_count"] if row["messages_count"] is not None else 0
        stats["message_count"] = max(stats["message_count"], db_messages, extra_messages)
        stats["voice_seconds"] = max(stats["voice_seconds"], row["voice_seconds"] or 0)
        if row["last_active"]:
            stats["last_active"] = row["last_active"]
        stats["voice_hours"] = float(row["voice_hours"] or (stats["voice_seconds"] / 3600.0))
        stats["level"] = row["level"] or 1
        stats["su_coins"] = row["su_coins"] or 0
        return stats

    @app_commands.command(name="活躍統計", description="查看自己的文字、語音與最後活躍時間")
    async def my_activity_stats(self, interaction: discord.Interaction):
        stats = self._collect_stats(interaction.user.id)
        voice_hours = stats["voice_hours"]
        if voice_hours <= 0 and stats["voice_seconds"]:
            voice_hours = round(stats["voice_seconds"] / 3600.0, 2)

        embed = discord.Embed(
            title=f"📈 {interaction.user.display_name} 的活躍統計",
            color=discord.Color.gold(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="💬 文字發言", value=f"`{stats['message_count']}` 則", inline=True)
        embed.add_field(name="🎙️ 語音時數", value=f"`{voice_hours:.1f}` 小時", inline=True)
        embed.add_field(name="📊 等級", value=f"Lv. {stats['level']}", inline=True)
        embed.add_field(name="💰 SU 幣", value=f"`{stats['su_coins']}` 枚", inline=True)
        embed.add_field(name="⏱️ 最後活躍", value=str(stats["last_active"]), inline=False)
        embed.set_footer(text=f"資料檔：{os.path.basename(DATA_FILE)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ActivityStatsCog(bot))
