# ==================================================
# 檔案名稱：utils/roles.py
# 檔案用途：公會身分組 ID／名稱對應（一律使用繁體）
# ==================================================

import discord

# Discord 身分組 ID（鍵只用繁體，避免 會/会 混用對不到）
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
    "2會": 1541087803151098079,
    "3會": 1541087848298446998,
}

MEMBER_ROLE_ID = ROLE_IDS["成員"]
MEMBER_ROLE_NAME = "成員"
FRIEND_ROLE_NAME = "好朋友"

CLASS_ALIASES = {
    "聖騎士": "聖騎",
    "圣骑": "聖騎",
    "狂戰士": "戰士",
}

BRANCH_NAME_HINTS = {
    "1會": ("1會", "Escalation 1會", "Escalation I", "Escalation 1"),
    "2會": ("2會", "Escalation II", "Escalation 2會", "Escalation 2"),
    "3會": ("3會", "Escalation III", "Escalation 3會", "Escalation 3"),
}


def normalize_branch_label(value: str) -> str:
    """簡體「会」一律轉成繁體「會」。"""
    text = (value or "").strip().replace("会", "會")
    if text in ("1會", "2會", "3會"):
        return text
    return text


def normalize_class_key(value: str) -> str:
    text = (value or "").strip()
    return CLASS_ALIASES.get(text, text)


def resolve_guild_role(guild, key: str):
    """先用 ID，找不到再依繁體名稱 / Escalation I·II·III 名稱搜尋。"""
    if guild is None or not key:
        return None
    key = normalize_branch_label(key)
    key = normalize_class_key(key)
    role_id = ROLE_IDS.get(key)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role
    hints = BRANCH_NAME_HINTS.get(key, (key,))
    wanted = {h.lower() for h in hints}
    wanted.add(key.lower())
    for role in guild.roles:
        name = (role.name or "").strip()
        if name.lower() in wanted:
            return role
        compact = name.replace(" ", "").lower().replace("会", "會")
        if compact in {h.replace(" ", "").lower() for h in hints}:
            return role
    return discord.utils.get(guild.roles, name=key)


def find_friend_role(guild):
    if guild is None:
        return None
    return discord.utils.get(guild.roles, name=FRIEND_ROLE_NAME)


async def fetch_guild_member(guild, user_id):
    if guild is None or not user_id:
        return None
    member = guild.get_member(int(user_id))
    if member:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except Exception:
        return None


async def grant_onboarding_roles(member, main_class: str, branch: str):
    """發放成員＋職業＋分會，並移除好朋友。回傳實際結果說明。"""
    granted = []
    missing = []
    removed = []
    error = ""
    if member is None:
        return granted, missing, removed, "找不到該成員（可能已退出或快取沒載到）"

    guild = member.guild
    to_add = []
    checks = [
        ("成員", "成員"),
        (normalize_class_key(main_class), f"職業 {main_class}"),
        (normalize_branch_label(branch), f"分會 {normalize_branch_label(branch)}"),
    ]
    for key, label in checks:
        if not key:
            missing.append(label)
            continue
        role = resolve_guild_role(guild, key)
        if role is None:
            missing.append(label)
            continue
        if role not in member.roles:
            to_add.append(role)
        granted.append(f"{label}（{role.name}）")

    friend_role = find_friend_role(guild)
    to_remove = []
    if friend_role and friend_role in member.roles:
        to_remove.append(friend_role)
        removed.append(FRIEND_ROLE_NAME)

    try:
        if to_add:
            await member.add_roles(*to_add, reason="入會審核通過")
        if to_remove:
            await member.remove_roles(*to_remove, reason="入會轉正，移除好朋友")
    except discord.Forbidden:
        error = "機器人沒有管理身分組權限，或機器人身分組順位低於要發放的身分組"
    except Exception as exc:
        error = str(exc)
    return granted, missing, removed, error
