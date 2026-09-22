# ==================================================
# 檔案名稱：utils/level_helper.py
# 檔案用途：公用經驗值核心管理庫（含 XP 增加、升級判定與 Lv.50 滿等封頂機制）
# ==================================================

from utils.database import load_data, save_data

def add_user_xp(user_id: str, user_name: str, xp_amount: int):
    """
    共用加經驗值函式（含滿等封頂保護）
    :param user_id: 成員 Discord ID (字串)
    :param user_name: 成員名稱
    :param xp_amount: 要增加的經驗值數量
    :return: dict (包含是否升級、新等級、新經驗值等狀態)
    """
    data = load_data()
    
    if "leveling_system" not in data:
        data["leveling_system"] = {}

    users = data["leveling_system"]
    if user_id not in users:
        users[user_id] = {"name": user_name, "xp": 0, "level": 1}

    current_level = users[user_id]["level"]
    
    # 🛡️ 已經達到滿等 (Lv. 50) 的成員，直接鎖定不再增加經驗值與等級
    MAX_LEVEL = 50
    if current_level >= MAX_LEVEL:
        users[user_id]["name"] = user_name
        users[user_id]["level"] = MAX_LEVEL
        users[user_id]["xp"] = 0  # 滿等後經驗值歸零或固定
        save_data(data)
        return {
            "leveled_up": False,
            "old_level": MAX_LEVEL,
            "new_level": MAX_LEVEL,
            "current_xp": 0,
            "xp_needed": MAX_LEVEL * 100,
            "is_max_level": True
        }

    # 更新名稱與增加經驗值
    users[user_id]["name"] = user_name
    users[user_id]["xp"] += xp_amount

    current_xp = users[user_id]["xp"]
    xp_needed = current_level * 100

    leveled_up = False
    old_level = current_level

    # 檢查是否升級（支援一次獲得大量 XP 直接連跳多級的防呆迴圈）
    while current_xp >= xp_needed and current_level < MAX_LEVEL:
        current_level += 1
        current_xp -= xp_needed
        leveled_up = True
        
        # 如果升級後剛好達到 50 等，直接封頂並終止迴圈
        if current_level >= MAX_LEVEL:
            current_level = MAX_LEVEL
            current_xp = 0  # 封頂後多餘經驗值清空
            break
            
        xp_needed = current_level * 100  # 更新下一級所需門檻

    # 回寫資料庫
    users[user_id]["level"] = current_level
    users[user_id]["xp"] = current_xp
    save_data(data)

    return {
        "leveled_up": leveled_up,
        "old_level": old_level,
        "new_level": current_level,
        "current_xp": current_xp,
        "xp_needed": xp_needed,
        "is_max_level": (current_level >= MAX_LEVEL)
    }
