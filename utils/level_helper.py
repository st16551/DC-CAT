# ==================================================
# 檔案名稱：utils/level_helper.py
# 檔案用途：公用經驗值核心（與 /我的面板、簽到、語音獎勵共用同一套門檻）
# ==================================================

from utils.database import get_db_connection

MAX_LEVEL = 50
DEFAULT_MAX_EXP = 100


def add_user_xp(user_id: str, user_name: str, xp_amount: int, count_message: bool = False):
    """
    增加經驗值。預設不增加發言數（語音/簽到不應被算成訊息）。
    升級門檻與 leveling cog 一致：初始 100，每升一級 * 1.2。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    uid = int(user_id)

    cursor.execute(
        """
        SELECT level, exp, max_exp, messages_count
        FROM member_levels WHERE discord_id = ?
        """,
        (uid,),
    )
    row = cursor.fetchone()

    if not row:
        current_level = 1
        current_xp = 0
        max_exp = DEFAULT_MAX_EXP
        messages_count = 0
        cursor.execute(
            """
            INSERT OR IGNORE INTO member_levels
            (discord_id, level, su_coins, messages_count, voice_hours, exp, max_exp)
            VALUES (?, 1, 0, 0, 0.0, 0, 100)
            """,
            (uid,),
        )
    else:
        current_level = row["level"] or 1
        current_xp = row["exp"] or 0
        max_exp = row["max_exp"] or DEFAULT_MAX_EXP
        messages_count = row["messages_count"] or 0

    if count_message:
        messages_count += 1

    if current_level >= MAX_LEVEL:
        cursor.execute(
            """
            UPDATE member_levels
            SET level = ?, exp = 0, messages_count = ?, max_exp = ?
            WHERE discord_id = ?
            """,
            (MAX_LEVEL, messages_count, max_exp, uid),
        )
        conn.commit()
        conn.close()
        return {
            "leveled_up": False,
            "old_level": MAX_LEVEL,
            "new_level": MAX_LEVEL,
            "current_xp": 0,
            "xp_needed": max_exp,
            "is_max_level": True,
        }

    current_xp += xp_amount
    leveled_up = False
    old_level = current_level

    while current_xp >= max_exp and current_level < MAX_LEVEL:
        current_level += 1
        current_xp -= max_exp
        leveled_up = True
        max_exp = int(max_exp * 1.2)
        if current_level >= MAX_LEVEL:
            current_level = MAX_LEVEL
            current_xp = 0
            break

    cursor.execute(
        """
        UPDATE member_levels
        SET level = ?, exp = ?, messages_count = ?, max_exp = ?
        WHERE discord_id = ?
        """,
        (current_level, current_xp, messages_count, max_exp, uid),
    )
    conn.commit()
    conn.close()

    return {
        "leveled_up": leveled_up,
        "old_level": old_level,
        "new_level": current_level,
        "current_xp": current_xp,
        "xp_needed": max_exp,
        "is_max_level": current_level >= MAX_LEVEL,
    }
