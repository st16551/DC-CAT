import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_db_connection
from utils.sheets import (
    apply_display_name_profile,
    discord_member_display_name,
    load_sheet_profile,
    normalize_class_name,
    resolve_branch,
    sync_member_by_discord_id,
)

ROLE_IDS = {
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


def _row_value(row, index, key=None):
    if row is None:
        return ""
    try:
        if key and hasattr(row, "keys") and key in row.keys():
            return row[key] or ""
    except Exception:
        pass
    try:
        return row[index] or ""
    except Exception:
        return ""


def load_member_edit_prefill(member: discord.Member):
    """資料庫 → 試算表 → Discord 暱稱，缺一層就往下一層補。"""
    target_id = int(member.id)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT discord_id, discord_name, game_name, character_name, main_class, branch
        FROM game_characters
        WHERE discord_id = ? OR CAST(discord_id AS TEXT) = ?
        """,
        (target_id, str(target_id)),
    )
    db_row = cursor.fetchone()
    conn.close()

    display_name = discord_member_display_name(member)
    nick_profile = {}
    apply_display_name_profile(nick_profile, display_name)

    sheet_profile = None
    try:
        sheet_profile = load_sheet_profile(target_id)
    except Exception as exc:
        print(f"讀取試算表預填失敗：{exc}")
        sheet_profile = None

    character_name = (
        _row_value(db_row, 3, "character_name")
        or (sheet_profile or {}).get("character_name")
        or nick_profile.get("character_name")
        or ""
    )
    main_class = normalize_class_name(
        _row_value(db_row, 4, "main_class")
        or (sheet_profile or {}).get("main_class")
        or nick_profile.get("main_class")
        or ""
    )
    branch = resolve_branch(
        _row_value(db_row, 5, "branch"),
        (sheet_profile or {}).get("branch"),
    )
    discord_name = (
        _row_value(db_row, 1, "discord_name")
        or display_name
        or str(member)
    )
    game_name = _row_value(db_row, 2, "game_name") or "靈谷"
    return (
        target_id,
        discord_name,
        game_name,
        character_name,
        main_class,
        branch,
    )


class EditMemberByDiscordModal(discord.ui.Modal, title="🛠️ 修改成員資料"):
    def __init__(self, target_discord_id: int, db_data):
        super().__init__()
        self.target_discord_id = target_discord_id
        self.db_data = db_data

        self.new_char_name_input = discord.ui.TextInput(
            label="新遊戲角色 ID",
            default=db_data[3] if db_data else "",
            max_length=50,
            required=True
        )
        self.class_input = discord.ui.TextInput(
            label="新職業 (聖騎/戰士/法師/死靈/牧師/槍手/忍者/編織)",
            default=db_data[4] if db_data else "聖騎",
            max_length=20,
            required=True
        )
        self.branch_input = discord.ui.TextInput(
            label="新分配分會 (1會 / 2會 / 3會)",
            default=db_data[5] if db_data else "1會",
            max_length=10,
            required=True
        )

        self.add_item(self.new_char_name_input)
        self.add_item(self.class_input)
        self.add_item(self.branch_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_char_name = self.new_char_name_input.value.strip()
        new_class = normalize_class_name(self.class_input.value.strip())
        new_branch = self.branch_input.value.strip()
        if new_branch == "2会":
            new_branch = "2會"
        if new_branch == "3会":
            new_branch = "3會"

        if new_branch not in ["1會", "2會", "3會"]:
            await interaction.response.send_message("❌ 分會名稱必須是 `1會`、`2會` 或 `3會`！", ephemeral=True)
            return

        old_char_name = self.db_data[3] if self.db_data else "未知"
        old_class = self.db_data[4] if self.db_data else ""
        old_branch = self.db_data[5] if self.db_data else ""
        member = (
            interaction.guild.get_member(self.target_discord_id)
            if interaction.guild
            else None
        )
        discord_name = (
            discord_member_display_name(member)
            or (self.db_data[1] if self.db_data else "")
            or str(self.target_discord_id)
        )

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_characters (
                discord_id, discord_name, game_name, character_name, main_class, branch
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                discord_name = excluded.discord_name,
                character_name = excluded.character_name,
                main_class = excluded.main_class,
                branch = excluded.branch
            """,
            (
                self.target_discord_id,
                discord_name,
                "靈谷",
                new_char_name,
                new_class,
                new_branch,
            ),
        )
        conn.commit()
        conn.close()

        sheet_updated = False
        sheet_error = ""
        try:
            synced = sync_member_by_discord_id(
                self.target_discord_id,
                member=member,
                extra_profile={
                    "discord_name": discord_name,
                    "character_name": new_char_name,
                    "main_class": new_class,
                    "branch": new_branch,
                },
                force=True,
            )
            sheet_updated = synced is not None
            if not sheet_updated:
                sheet_error = "寫入後沒有回傳列資料"
        except Exception as e:
            sheet_error = str(e)
            print(f"❌ 同步 Google 試算表失敗：{e}")

        guild = interaction.guild
        role_changes_msg = []

        if member:
            if old_class != new_class:
                if old_class and old_class in ROLE_IDS:
                    old_r = guild.get_role(ROLE_IDS[old_class])
                    if old_r and old_r in member.roles:
                        await member.remove_roles(old_r)
                if new_class in ROLE_IDS:
                    new_r = guild.get_role(ROLE_IDS[new_class])
                    if new_r:
                        await member.add_roles(new_r)
                        role_changes_msg.append(f"職業: {new_class}")

            if old_branch != new_branch:
                if old_branch and old_branch in ROLE_IDS:
                    old_br = guild.get_role(ROLE_IDS[old_branch])
                    if old_br and old_br in member.roles:
                        await member.remove_roles(old_br)
                if new_branch in ROLE_IDS:
                    new_br = guild.get_role(ROLE_IDS[new_branch])
                    if new_br:
                        await member.add_roles(new_br)
                        role_changes_msg.append(f"分會: {new_branch}")

        sheet_line = "成功" if sheet_updated else f"失敗{('：' + sheet_error) if sheet_error else ''}"
        await interaction.response.send_message(
            f"✅ **成功修改並替換成員資料！**\n"
            f"• 成員：{member.mention if member else f'<@{self.target_discord_id}>'}\n"
            f"• 原遊戲角色 ID：`{old_char_name}`\n"
            f"• 新遊戲角色 ID：`{new_char_name}`\n"
            f"• 新職業：`{new_class}`\n"
            f"• 新分會：`{new_branch}`\n"
            f"• 📁 試算表同步：{sheet_line}\n"
            f"• 🛡️ 身分組異動：{', '.join(role_changes_msg) if role_changes_msg else '無需調整'}",
            ephemeral=True
        )


class EditMemberCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="修改成員資料",
        description="【幹部專用】直接點選或標註成員，線上修改並更新其遊戲角色、職業與分會"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    async def edit_member(self, interaction: discord.Interaction, member: discord.Member):
        prefill = load_member_edit_prefill(member)
        modal = EditMemberByDiscordModal(
            target_discord_id=int(member.id),
            db_data=prefill,
        )
        await interaction.response.send_modal(modal)

async def setup(bot):
    await bot.add_cog(EditMemberCog(bot))
