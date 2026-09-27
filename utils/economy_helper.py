# ==================================================
# 檔案名稱：utils/economy_helper.py
# 檔案用途：公用經濟核心（統一 SQLite 絕對路徑）
# ==================================================

from utils.database import DATA_FILE, DB_FILE, ECONOMY_DB_FILE, get_db_connection

ECONOMY_DB_FILE = DB_FILE


def update_user_coins(user_id: str, user_name: str, amount: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    uid = int(user_id)

    cursor.execute(
        "SELECT su_coins FROM member_levels WHERE discord_id = ?",
        (uid,),
    )
    row = cursor.fetchone()

    if not row:
        current_coins = 0
        cursor.execute(
            """
            INSERT OR IGNORE INTO member_levels
            (discord_id, level, su_coins, messages_count, voice_hours, exp, max_exp)
            VALUES (?, 1, 0, 0, 0.0, 0, 100)
            """,
            (uid,),
        )
    else:
        current_coins = row["su_coins"] if row["su_coins"] is not None else 0

    success = True
    if amount < 0 and (current_coins + amount) < 0:
        success = False
        new_balance = current_coins
    else:
        new_balance = max(0, current_coins + amount)

    if success:
        cursor.execute(
            "UPDATE member_levels SET su_coins = ? WHERE discord_id = ?",
            (new_balance, uid),
        )
        conn.commit()

    conn.close()
    return {"success": success, "new_balance": new_balance}


def get_wallet_balance(discord_id) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT su_coins FROM member_levels WHERE discord_id = ?",
        (int(discord_id),),
    )
    row = cursor.fetchone()
    conn.close()
    if row and row["su_coins"] is not None:
        return int(row["su_coins"])
    return 0


def modify_balance(user_id: str, user_name: str, amount: int):
    return update_user_coins(user_id, user_name, amount)
