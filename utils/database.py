# ==================================================
# 檔案名稱：utils/database.py
# 檔案用途：SQLite 資料庫核心初始化與連線管理
# ==================================================

import sqlite3
import json
import os

DB_FILE = "guild_database.db"
JSON_DB_PATH = "guild_data.json"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. 會員與活躍度表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. 遊戲角色表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            game_name TEXT,
            character_name TEXT,
            main_class TEXT,
            FOREIGN KEY (discord_id) REFERENCES users (discord_id)
        )
    """)
    
    # 3. 請假紀錄表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            reason TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT '審核中',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (discord_id) REFERENCES users (discord_id)
        )
    """)

    # 4. 意見回饋箱表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            feedback_id TEXT PRIMARY KEY,
            discord_id INTEGER,
            author_name TEXT,
            content TEXT,
            status TEXT DEFAULT '審核中',
            handler TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (discord_id) REFERENCES users (discord_id)
        )
    """)

    # 5. 簽到系統表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkin_system (
            discord_id INTEGER PRIMARY KEY,
            name TEXT,
            last_date TEXT,
            streak INTEGER DEFAULT 0
        )
    """)

    # 6. 會員成長數據與資產表（確保舊資料欄位完整）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_levels (
            discord_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            su_coins INTEGER DEFAULT 0,
            messages_count INTEGER DEFAULT 0,
            voice_hours REAL DEFAULT 0.0,
            exp INTEGER DEFAULT 0,
            max_exp INTEGER DEFAULT 100
        )
    """)
    
    conn.commit()
    conn.close()

# ❌ 刪除原本底部的自動執行：init_db()

def load_data():
    if not os.path.exists(JSON_DB_PATH):
        return {}
    try:
        with open(JSON_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_data(data):
    with open(JSON_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
