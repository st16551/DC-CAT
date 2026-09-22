# ==================================================
# 檔案名稱：database.py
# 檔案用途：共用 JSON 資料庫讀寫核心
# ==================================================

import json
import os

DATA_FILE = "data.json"

def load_data() -> dict:
    """讀取 data.json，若檔案不存在或損壞則回傳空字典"""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_data(data: dict):
    """將資料寫入 data.json"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
