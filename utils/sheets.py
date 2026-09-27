# ==================================================
# 檔案名稱：utils/sheets.py
# 檔案用途：Google 試算表統一連線（支援 Render 的 GOOGLE_CREDENTIALS 環境變數）
# ==================================================

import json
import os

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = os.getenv(
    "SPREADSHEET_ID", "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
)
MEMBER_SHEET_NAME = os.getenv("MEMBER_SHEET_NAME", "成員名單")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ROLE_ALIASES = {
    "聖騎士": "聖騎",
    "圣骑": "聖騎",
    "2會": "2会",
    "3會": "3会",
}


def normalize_class_name(name: str) -> str:
    if not name:
        return name
    return ROLE_ALIASES.get(name.strip(), name.strip())


def get_gspread_client():
    creds_json_str = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)


def get_member_sheet():
    client = get_gspread_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(MEMBER_SHEET_NAME)
    except Exception:
        return spreadsheet.sheet1


def format_member_display(row):
    """相容兩種欄位排版：機器人寫入版 / 舊公開 CSV 版。"""
    if not row:
        return ""
    cells = [(c or "").strip() for c in row]
    first = cells[0] if cells else ""
    if first.isdigit() and len(cells) >= 4:
        discord_name = cells[1] if len(cells) > 1 else ""
        character_name = cells[2] if len(cells) > 2 else ""
        job = cells[3] if len(cells) > 3 else ""
        if job and character_name:
            return f"{job}-{character_name}({discord_name})"
        return character_name or discord_name
    discord_account = cells[1] if len(cells) > 1 else ""
    game_name = cells[2] if len(cells) > 2 else ""
    job = cells[3] if len(cells) > 3 else ""
    if job and game_name:
        return f"{job}-{game_name}({discord_account})"
    return game_name or discord_account
