# ==================================================
# 檔案名稱：utils/database.py
# 檔案用途：SQLite 資料庫核心初始化與連線管理
# ==================================================

import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "guild_database.db")
ECONOMY_DB_FILE = DB_FILE
JSON_DB_PATH = os.path.join(BASE_DIR, "guild_data.json")
DATA_FILE = JSON_DB_PATH


def get_db_connection():
    """提供統一的資料庫連線（絕對路徑，所有模組共用同一檔案）"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns(cursor, table: str, columns: dict[str, str]):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {col[1] for col in cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message_count INTEGER DEFAULT 0,
            voice_seconds INTEGER DEFAULT 0
        )
        """
    )
    _ensure_columns(
        cursor,
        "users",
        {
            "message_count": "INTEGER DEFAULT 0",
            "voice_seconds": "INTEGER DEFAULT 0",
            "joined_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "last_active": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS game_characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER UNIQUE,
            discord_name TEXT,
            game_name TEXT,
            character_name TEXT,
            main_class TEXT,
            branch TEXT DEFAULT '未分配'
        )
        """
    )
    _ensure_columns(
        cursor,
        "game_characters",
        {
            "discord_name": "TEXT",
            "game_name": "TEXT",
            "character_name": "TEXT",
            "main_class": "TEXT",
            "branch": "TEXT DEFAULT '未分配'",
        },
    )

    cursor.execute(
        """
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
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feedbacks (
            feedback_id TEXT PRIMARY KEY,
            discord_id INTEGER,
            author_id INTEGER,
            author_name TEXT,
            content TEXT,
            status TEXT DEFAULT '審核中',
            handler TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_columns(
        cursor,
        "feedbacks",
        {
            "discord_id": "INTEGER",
            "author_id": "INTEGER",
            "author_name": "TEXT",
            "handler": "TEXT",
        },
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS checkin_system (
            discord_id INTEGER PRIMARY KEY,
            name TEXT,
            last_date TEXT,
            streak INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS member_levels (
            discord_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            su_coins INTEGER DEFAULT 0,
            messages_count INTEGER DEFAULT 0,
            voice_hours REAL DEFAULT 0.0,
            exp INTEGER DEFAULT 0,
            max_exp INTEGER DEFAULT 100
        )
        """
    )
    _ensure_columns(
        cursor,
        "member_levels",
        {"exp": "INTEGER DEFAULT 0", "max_exp": "INTEGER DEFAULT 100"},
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS active_debuffs (
            id TEXT PRIMARY KEY,
            guild_id INTEGER,
            user_id INTEGER,
            type TEXT,
            old_nickname TEXT,
            expire_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            prize TEXT,
            winners_count INTEGER,
            end_timestamp REAL,
            participants TEXT,
            ended INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS loot_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_name TEXT,
            leader_discord_id INTEGER,
            item_name TEXT,
            loot_date TEXT,
            members TEXT,
            total_price REAL,
            tax_rate REAL,
            status TEXT DEFAULT 'pending',
            updated_by TEXT,
            updated_at TEXT,
            edit_summary TEXT
        )
        """
    )
    _ensure_columns(
        cursor,
        "loot_projects",
        {
            "leader_discord_id": "INTEGER",
            "edit_summary": "TEXT",
            "updated_by": "TEXT",
            "updated_at": "TEXT",
        },
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS split_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            member_name TEXT,
            item_name TEXT,
            total_per_person REAL,
            leader_name TEXT,
            status INTEGER DEFAULT 0,
            message_id INTEGER,
            channel_id INTEGER,
            FOREIGN KEY(project_id) REFERENCES loot_projects(id)
        )
        """
    )
    _ensure_columns(
        cursor,
        "split_records",
        {
            "project_id": "INTEGER",
            "message_id": "INTEGER",
            "channel_id": "INTEGER",
        },
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS raid_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            channel_id INTEGER,
            role_name TEXT,
            member_name TEXT,
            leader_name TEXT,
            title TEXT
        )
        """
    )

    try:
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_game_characters_discord_id ON game_characters(discord_id)"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def load_data():
    if not os.path.exists(JSON_DB_PATH):
        return {}
    try:
        with open(JSON_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_json_data(data):
    with open(JSON_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_data(data_or_file, data=None):
    """相容兩種呼叫：save_data(dict) 或 save_data(filename, dict)。"""
    if data is None:
        save_json_data(data_or_file)
        return
    payload = load_data()
    payload["custom_raid_configs"] = data
    save_json_data(payload)
