# ==================================================
# 檔案名稱：utils/level_helper.py
# 檔案用途：公用經驗值核心管理庫（統一處理各模組的 XP 增加與升級判定）
# ==================================================

from utils.database import load_data, save_data

def add_user_xp(user_id: str, user_name: str, xp_amount: int):
    """
    共用加經驗值函式
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

    # 更新名稱與增加經驗值
    users[user_id]["name"] = user_name
    users[user_id]["xp"] += xp_amount

    current_level = users[user_id]["level"]
    current_xp = users[user_id]["xp"]
    xp_needed = current_level * 100

    leveled_up = False
    old_level = current_level

    # 檢查是否升級（支援一次獲得大量 XP 直接連跳多級的防呆迴圈）
    while current_xp >= xp_needed:
        current_level += 1
        current_xp -= xp_needed
        leveled_up = True
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
        "xp_needed": xp_needed
    }
