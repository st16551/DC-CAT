# ==================================================
# 檔案名稱：utils/level_helper.py
# 檔案用途：公用經驗值核心管理庫（已完美對應 SQLite 資料庫與雲端備份）
# ==================================================

import sqlite3

DB_FILE = "guild_database.db"

def add_user_xp(user_id: str, user_name: str, xp_amount: int):
    """
    共用加經驗值函式（直接操作 SQLite 資料庫，支援滿等封頂與防呆機制）
    :param user_id: 成員 Discord ID (字串或整數)
    :param user_name: 成員名稱
    :param xp_amount: 要增加的經驗值數量
    :return: dict (包含是否升級、新等級、新經驗值等狀態)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    uid = int(user_id)
    MAX_LEVEL = 50

    # 1. 查詢或初始化該成員在 member_levels 的資料
    cursor.execute("""
        SELECT level, exp, messages_count, voice_hours, su_coins 
        FROM member_levels WHERE discord_id = ?
    """, (uid,))
    row = cursor.fetchone()

    if not row:
        # 如果資料庫還沒有這個人，先初始化一筆預設值
        current_level = 1
        current_xp = 0
        messages_count = 0
        voice_hours = 0.0
        su_coins = 0
        cursor.execute("""
            INSERT OR IGNORE INTO member_levels (discord_id, level, su_coins, messages_count, voice_hours, exp)
            VALUES (?, 1, 0, 0, 0.0, 0)
        """, (uid,))
    else:
        current_level, current_xp, messages_count, voice_hours, su_coins = row

    # 2. 自動增加文字發言數（每次觸發加 XP 通常代表發了一則訊息）
    messages_count += 1

    # 3. 🛡️ 已經達到滿等 (Lv. 50) 的成員保護機制
    if current_level >= MAX_LEVEL:
        cursor.execute("""
            UPDATE member_levels 
            SET level = ?, exp = 0, messages_count = ? 
            WHERE discord_id = ?
        """, (MAX_LEVEL, messages_count, uid))
        conn.commit()
        conn.close()
        return {
            "leveled_up": False,
            "old_level": MAX_LEVEL,
            "new_level": MAX_LEVEL,
            "current_xp": 0,
            "xp_needed": MAX_LEVEL * 100,
            "is_max_level": True
        }

    # 4. 正常累積經驗值與升級判定
    current_xp += xp_amount
    xp_needed = current_level * 100

    leveled_up = False
    old_level = current_level

    # 支援一次獲得大量 XP 直接連跳多級的防呆迴圈
    while current_xp >= xp_needed and current_level < MAX_LEVEL:
        current_level += 1
        current_xp -= xp_needed
        leveled_up = True
        
        if current_level >= MAX_LEVEL:
            current_level = MAX_LEVEL
            current_xp = 0  # 封頂後多餘經驗值清空
            break
            
        xp_needed = current_level * 100

    # 5. 將最新數據寫回 SQLite 資料庫
    cursor.execute("""
        UPDATE member_levels 
        SET level = ?, exp = ?, messages_count = ? 
        WHERE discord_id = ?
    """, (current_level, current_xp, messages_count, uid))
    
    conn.commit()
    conn.close()

    return {
        "leveled_up": leveled_up,
        "old_level": old_level,
        "new_level": current_level,
        "current_xp": current_xp,
        "xp_needed": xp_needed,
        "is_max_level": (current_level >= MAX_LEVEL)
    }
