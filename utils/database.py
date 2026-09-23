# utils/database_sqlite.py
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

    # 4. 意見回饋箱表 (全面收編進 SQLite)
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
    
    conn.commit()
    conn.close()

# 程式載入時自動建立表格
init_db()
