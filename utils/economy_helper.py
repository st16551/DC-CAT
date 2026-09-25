# ==================================================
# 檔案名稱：utils/economy_helper.py
# 檔案用途：公用經濟核心管理庫（已完美對應 SQLite 資料庫與雲端備份）
# ==================================================

import sqlite3

DB_FILE = "guild_database.db"

def update_user_coins(user_id: str, user_name: str, amount: int):
    """
    共用金幣調整函式（直接操作 SQLite 資料庫，含防負數底線保護）
    :param user_id: 成員 Discord ID (字串或整數)
    :param user_name: 成員名稱
    :param amount: 調整數量（正數為增加，負數為扣除）
    :return: dict (包含更新後的最新餘額與是否成功)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    uid = int(user_id)

    # 1. 查詢或初始化該成員在 member_levels 的資料
    cursor.execute("""
        SELECT su_coins, level, exp, messages_count, voice_hours 
        FROM member_levels WHERE discord_id = ?
    """, (uid,))
    row = cursor.fetchone()

    if not row:
        current_coins = 0
        cursor.execute("""
            INSERT OR IGNORE INTO member_levels (discord_id, level, su_coins, messages_count, voice_hours, exp)
            VALUES (?, 1, 0, 0, 0.0, 0)
        """, (uid,))
    else:
        current_coins = row[0]

    # 2. 計算調整後的餘額（透過 max(0, ...) 確保餘額絕對不會小於 0）
    new_balance = max(0, current_coins + amount)
    
    # 3. 檢查扣款是否合法（若扣款後會小於 0 則判定交易失敗）
    success = True
    if amount < 0 and (current_coins + amount) < 0:
        success = False
        new_balance = current_coins  # 扣款失敗時維持原餘額不變

    # 4. 如果判定成功，將最新餘額寫回 SQLite 資料庫
    if success:
        cursor.execute("""
            UPDATE member_levels 
            SET su_coins = ? 
            WHERE discord_id = ?
        """, (new_balance, uid))
        conn.commit()

    conn.close()

    return {
        "success": success,
        "new_balance": new_balance
    }

def get_wallet_balance(discord_id: int) -> int:
    """取得使用者的錢包餘額 (su_coins)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT su_coins FROM member_levels WHERE discord_id = ?", (int(discord_id),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return 0

def modify_balance(user_id: str, user_name: str, amount: int):
    """修改使用者金幣的相容包裝函數"""
    return update_user_coins(user_id, user_name, amount)
