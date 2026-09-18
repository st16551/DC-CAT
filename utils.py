import os
import json
import sqlite3
import discord

DATA_FILE = "activity_data.json"
CUSTOM_CONFIG_FILE = "custom_raid_configs.json"
ECONOMY_DB_FILE = "economy.db"

def load_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(file_path, data):
    temp_file = file_path + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(temp_file, file_path)

activity_data = load_data(DATA_FILE)
custom_configs = load_data(CUSTOM_CONFIG_FILE)

# 讓 raid.py 與 activity_stats.py 共用的暫時語音房紀錄
temp_voice_rooms = {}


# ==========================================
# SU幣與經濟系統底層（SQLite 雙表與交易安全）
# ==========================================

def init_economy_db():
    """初始化 SU幣專用資料庫，建立錢包與交易日誌表"""
    conn = sqlite3.connect(ECONOMY_DB_FILE)
    cursor = conn.cursor()
    
    # 錢包表：記錄每個用戶的餘額
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id TEXT PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    """)
    
    # 交易日誌表：記錄每一筆 SU幣異動，確保帳目可追溯
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id TEXT,
            receiver_id TEXT,
            amount INTEGER,
            tx_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

# 啟動時自動初始化資料庫
init_economy_db()

def get_wallet_balance(user_id: str) -> int:
    """查詢指定用戶的 SU幣餘額"""
    conn = sqlite3.connect(ECONOMY_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def modify_balance(user_id: str, amount: int, tx_type: str = "system", sender_id: str = "SYSTEM") -> bool:
    """
    安全修改用戶餘額（具備交易認可與回滾保護）
    amount 可正可負。若扣款後餘額小於 0 則會自動攔截並回滾，回傳 False。
    """
    conn = sqlite3.connect(ECONOMY_DB_FILE)
    cursor = conn.cursor()
    
    try:
        # 開啟資料庫交易
        cursor.execute("BEGIN TRANSACTION")
        
        # 確保用戶錢包存在
        cursor.execute("INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)", (str(user_id),))
        
        # 查詢目前餘額
        cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (str(user_id),))
        current_balance = cursor.fetchone()[0]
        
        new_balance = current_balance + amount
        if new_balance < 0:
            # 餘額不足，取消交易
            conn.rollback()
            conn.close()
            return False
            
        # 更新餘額
        cursor.execute("UPDATE wallets SET balance = ? WHERE user_id = ?", (new_balance, str(user_id)))
        
        # 寫入交易日誌
        cursor.execute("""
            INSERT INTO transactions (sender_id, receiver_id, amount, tx_type)
            VALUES (?, ?, ?, ?)
        """, (str(sender_id), str(user_id), amount, tx_type))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"經濟系統交易錯誤: {e}")
        return False


# ==========================================
# 稱號與等級系統輔助函數
# ==========================================

LEVEL_TITLES = {
    50: {"name": "靈谷傳奇", "color": 0x9b59b6},
    30: {"name": "殿堂勇者", "color": 0xf1c40f},
    20: {"name": "迴響征服者", "color": 0xe67e22},
    10: {"name": "資深精銳", "color": 0x3498db},
    5:  {"name": "公會先鋒", "color": 0x2ecc71},
    1:  {"name": "新手冒險者", "color": 0x95a5a6}
}

ALL_LEVEL_TITLES = [data["name"] for data in LEVEL_TITLES.values()]

def get_title_by_level(level: int) -> str:
    if level >= 50:
        return "靈谷傳奇"
    elif level >= 30:
        return "殿堂勇者"
    elif level >= 20:
        return "迴響征服者"
    elif level >= 10:
        return "資深精銳"
    elif level >= 5:
        return "公會先鋒"
    else:
        return "新手冒險者"

def get_title_color(title_name: str) -> int:
    for data in LEVEL_TITLES.values():
        if data["name"] == title_name:
            return data["color"]
    return 0x95a5a6

async def assign_title_role(member: discord.Member, title_name: str, color_hex: int = 0x95a5a6):
    guild = member.guild
    for t_name in ALL_LEVEL_TITLES:
        if t_name != title_name:
            old_role = discord.utils.get(guild.roles, name=t_name)
            if old_role and old_role in member.roles:
                try:
                    await member.remove_roles(old_role)
                except discord.Forbidden:
                    pass

    role = discord.utils.get(guild.roles, name=title_name)
    if not role:
        try:
            role = await guild.create_role(name=title_name, color=discord.Color(color_hex), reason="公會系統自動建立稱號身分組")
        except discord.Forbidden:
            pass
    if role:
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            pass
