# ==================================================
# 檔案名稱：utils/economy_helper.py
# 檔案用途：公用經濟核心管理庫（統一處理各模組的 SU 幣增減與防負數安全機制）
# ==================================================

from utils.database import load_data, save_data

def update_user_coins(user_id: str, user_name: str, amount: int):
    """
    共用金幣調整函式（含防負數底線保護）
    :param user_id: 成員 Discord ID (字串)
    :param user_name: 成員名稱
    :param amount: 調整數量（正數為增加，負數為扣除）
    :return: dict (包含更新後的最新餘額與是否成功)
    """
    data = load_data()
    
    if "economy_system" not in data:
        data["economy_system"] = {}

    economy = data["economy_system"]
    if user_id not in economy:
        economy[user_id] = {"coins": 0, "name": user_name}

    economy[user_id]["name"] = user_name
    
    # 嚴格防呆：透過 max(0, ...) 確保餘額絕對不會被扣到負數
    new_balance = max(0, economy[user_id]["coins"] + amount)
    
    # 如果是扣錢但發現餘額不足（被 max 擋下來），可以回傳失敗讓商城阻擋交易
    success = True
    if amount < 0 and (economy[user_id]["coins"] + amount) < 0:
        success = False

    economy[user_id]["coins"] = new_balance
    save_data(data)

    return {
        "success": success,
        "new_balance": new_balance
    }
