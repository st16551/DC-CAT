# ==================================================
# 檔案名稱：utils/database.py
# 檔案用途：SQLite 資料庫核心初始化與連線管理
# ==================================================

import sqlite3

DB_FILE = "guild_database.db"

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

    # 5. 簽到系統表（確保 checkin.py 完美運行）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkin_system (
            discord_id INTEGER PRIMARY KEY,
            name TEXT,
            last_date TEXT,
            streak INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()

# 程式載入時自動建立所有資料表
init_db()
