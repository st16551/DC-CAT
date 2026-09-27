# ==================================================
# 檔案名稱：utils/sheets.py
# 檔案用途：Google 試算表連線（只讀 GOOGLE_CREDENTIALS）與成員狀態欄位同步
# ==================================================

import json
import os
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

from utils.database import get_db_connection

SPREADSHEET_ID = os.getenv(
    "SPREADSHEET_ID", "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
)
MEMBER_SHEET_NAME = os.getenv("MEMBER_SHEET_NAME", "成員名單")
INACTIVE_DAYS = int(os.getenv("INACTIVE_DAYS", "14"))

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

# A~I 固定欄位：人員完整資料 + 請假 / 活躍 / 未活躍
SHEET_HEADERS = [
    "Discord ID",
    "人員資料",
    "遊戲角色 ID",
    "職業",
    "分配分會",
    "入會時間",
    "請假",
    "活躍",
    "未活躍",
]


def normalize_class_name(name: str) -> str:
    if not name:
        return name
    return ROLE_ALIASES.get(name.strip(), name.strip())


def get_google_credentials_info():
    """只從環境變數 GOOGLE_CREDENTIALS 讀 JSON，絕不讀 credentials.json。"""
    raw = os.getenv("GOOGLE_CREDENTIALS")
    if raw is None or not str(raw).strip():
        raise RuntimeError(
            "找不到環境變數 GOOGLE_CREDENTIALS。請在 Render 貼上完整的服務帳戶 JSON。"
        )
    raw = str(raw).strip()
    if (raw.startswith("'") and raw.endswith("'")) or (
        raw.startswith('"') and raw.endswith('"')
    ):
        raw = raw[1:-1]
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS 不是合法 JSON。請貼上服務帳戶完整內容（含 type、client_email、private_key）。"
        ) from exc
    if not isinstance(info, dict):
        raise RuntimeError("GOOGLE_CREDENTIALS 必須是 JSON 物件。")
    private_key = info.get("private_key")
    if isinstance(private_key, str) and "\\n" in private_key and "\n" not in private_key:
        info["private_key"] = private_key.replace("\\n", "\n")
    return info


def get_gspread_client():
    info = get_google_credentials_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_member_sheet():
    client = get_gspread_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(MEMBER_SHEET_NAME)
    except Exception:
        return spreadsheet.sheet1


def format_member_display(row):
    """相容機器人寫入版 / 舊公開 CSV 版。"""
    if not row:
        return ""
    cells = [(c or "").strip() for c in row]
    if len(cells) > 1 and cells[1] and ("-" in cells[1] or "(" in cells[1]):
        return cells[1]
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


def build_personnel_label(job, character_name, discord_name, discord_id=None):
    job = (job or "").strip()
    character_name = (character_name or "").strip()
    discord_name = (discord_name or "").strip()
    if job and character_name and discord_name:
        return f"{job}-{character_name}({discord_name})"
    if job and character_name:
        return f"{job}-{character_name}"
    if character_name and discord_name:
        return f"{character_name}({discord_name})"
    return character_name or discord_name or (str(discord_id) if discord_id else "")


def parse_leave_range(start_str, end_str, now=None):
    now = now or datetime.now()
    if not start_str or not end_str:
        return None, None
    try:
        cleaned_s = str(start_str).replace("月", "/").replace("日", "").strip()
        cleaned_e = str(end_str).replace("月", "/").replace("日", "").strip()
        s_m, s_d = map(int, cleaned_s.split("/")[:2])
        e_m, e_d = map(int, cleaned_e.split("/")[:2])
        start_dt = datetime(now.year, s_m, s_d)
        end_dt = datetime(now.year, e_m, e_d, 23, 59, 59)
        if end_dt < start_dt:
            if now >= start_dt:
                end_dt = datetime(now.year + 1, e_m, e_d, 23, 59, 59)
            else:
                start_dt = datetime(now.year - 1, s_m, s_d)
        return start_dt, end_dt
    except Exception:
        return None, None


def _current_leave_text(discord_id, cursor, now):
    cursor.execute(
        """
        SELECT start_date, end_date, reason, status
        FROM leaves
        WHERE discord_id = ? AND status LIKE '%批准%'
        ORDER BY id DESC
        """,
        (int(discord_id),),
    )
    for row in cursor.fetchall():
        start_dt, end_dt = parse_leave_range(row["start_date"], row["end_date"], now)
        if start_dt and end_dt and start_dt <= now <= end_dt:
            reason = (row["reason"] or "").strip()
            period = f"{row['start_date']}~{row['end_date']}"
            return f"請假中 {period}" + (f"（{reason}）" if reason else ""), True
    return "", False


def _activity_fields(discord_id, cursor, now, days, on_leave, joined_at=None):
    threshold = now - timedelta(days=days)
    cursor.execute(
        """
        SELECT u.last_active, u.message_count, u.voice_seconds,
               m.messages_count, m.voice_hours
        FROM users u
        LEFT JOIN member_levels m ON u.discord_id = m.discord_id
        WHERE u.discord_id = ?
        """,
        (int(discord_id),),
    )
    row = cursor.fetchone()
    last_active_str = "從未記錄"
    last_active_time = None
    msg_count = 0
    voice_hours = 0.0

    if row:
        last_active_str = row["last_active"] or "從未記錄"
        msg_count = row["message_count"] or 0
        if row["messages_count"] is not None:
            msg_count = max(msg_count, row["messages_count"] or 0)
        voice_hours = float(row["voice_hours"] or 0)
        if (not voice_hours) and row["voice_seconds"]:
            voice_hours = round((row["voice_seconds"] or 0) / 3600.0, 2)
        if row["last_active"]:
            try:
                last_active_time = datetime.fromisoformat(str(row["last_active"]))
            except Exception:
                try:
                    last_active_time = datetime.strptime(
                        str(row["last_active"]), "%Y-%m-%d %H:%M:%S"
                    )
                except Exception:
                    last_active_time = None

    is_inactive = False
    inactive_reason = ""
    if on_leave:
        is_inactive = False
    elif last_active_time:
        if last_active_time < threshold:
            is_inactive = True
            inactive_reason = f"超過 {days} 天未互動（最後：{last_active_str}）"
    else:
        joined_dt = joined_at
        if isinstance(joined_dt, str) and joined_dt:
            try:
                joined_dt = datetime.fromisoformat(joined_dt.replace("Z", ""))
            except Exception:
                joined_dt = None
        if joined_dt is not None:
            try:
                if joined_dt.replace(tzinfo=None) < threshold:
                    is_inactive = True
                    inactive_reason = "長期無互動且無活動紀錄"
            except Exception:
                pass
        else:
            is_inactive = True
            inactive_reason = "尚無活躍紀錄"

    if on_leave:
        active_text = ""
        inactive_text = ""
    elif is_inactive:
        active_text = ""
        inactive_text = inactive_reason
    else:
        active_text = (
            f"是｜發言 {msg_count} 則｜語音 {voice_hours:.1f}h｜最後 {last_active_str}"
        )
        inactive_text = ""

    return active_text, inactive_text


def _joined_text(cursor, discord_id, fallback=None):
    if fallback:
        return str(fallback)
    try:
        cursor.execute(
            "SELECT joined_at FROM users WHERE discord_id = ?", (int(discord_id),)
        )
        row = cursor.fetchone()
        if row and row["joined_at"]:
            return str(row["joined_at"])
    except Exception:
        pass
    return ""


def build_member_sheet_row(profile: dict, cursor=None, now=None, days=None):
    """組成 A~I 一列完整人員資料。"""
    close_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        close_conn = True
    now = now or datetime.now()
    days = days if days is not None else INACTIVE_DAYS
    discord_id = profile.get("discord_id")
    job = profile.get("main_class") or ""
    character_name = profile.get("character_name") or ""
    discord_name = profile.get("discord_name") or ""
    branch = profile.get("branch") or ""
    joined = _joined_text(cursor, discord_id, profile.get("joined_at"))
    leave_text, on_leave = _current_leave_text(discord_id, cursor, now)
    active_text, inactive_text = _activity_fields(
        discord_id,
        cursor,
        now,
        days,
        on_leave,
        joined_at=profile.get("joined_at_dt"),
    )
    personnel = build_personnel_label(job, character_name, discord_name, discord_id)
    values = [
        str(discord_id),
        personnel,
        character_name,
        job,
        branch,
        joined,
        leave_text,
        active_text,
        inactive_text,
    ]
    if close_conn:
        cursor.connection.close()
    return values


def ensure_sheet_headers(sheet):
    current = sheet.row_values(1)
    if current[: len(SHEET_HEADERS)] != SHEET_HEADERS:
        sheet.update("A1:I1", [SHEET_HEADERS], value_input_option="USER_ENTERED")


def upsert_member_sheet_values(values):
    """用 A 欄 Discord ID 更新或新增一列 A~I。"""
    sheet = get_member_sheet()
    ensure_sheet_headers(sheet)
    discord_id = str(values[0]).strip()
    rows = sheet.get_all_values()
    target_row = None
    for index, row in enumerate(rows[1:], start=2):
        if row and str(row[0]).strip() == discord_id:
            target_row = index
            break
    if target_row:
        sheet.update(
            f"A{target_row}:I{target_row}",
            [values],
            value_input_option="USER_ENTERED",
        )
    else:
        sheet.append_row(values, value_input_option="USER_ENTERED")


def sync_member_by_discord_id(discord_id, member=None, extra_profile=None, days=None):
    """把單一成員的完整資料（含請假/活躍/未活躍）寫進試算表。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT discord_id, discord_name, character_name, main_class, branch
        FROM game_characters WHERE discord_id = ?
        """,
        (int(discord_id),),
    )
    row = cursor.fetchone()
    profile = extra_profile.copy() if extra_profile else {}
    profile["discord_id"] = int(discord_id)
    if row:
        profile.setdefault("discord_name", row["discord_name"] or "")
        profile.setdefault("character_name", row["character_name"] or "")
        profile.setdefault("main_class", row["main_class"] or "")
        profile.setdefault("branch", row["branch"] or "")
    if member is not None:
        profile.setdefault("discord_name", str(member))
        if getattr(member, "joined_at", None):
            profile["joined_at_dt"] = member.joined_at
            profile.setdefault(
                "joined_at",
                member.joined_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
    values = build_member_sheet_row(profile, cursor=cursor, days=days)
    conn.close()
    upsert_member_sheet_values(values)
    return values


def sync_all_members_to_sheet(guild, days=None):
    """把公會成員的人員資料、請假、活躍、未活躍一次寫回試算表。"""
    days = days if days is not None else INACTIVE_DAYS
    now = datetime.now()
    sheet = get_member_sheet()
    ensure_sheet_headers(sheet)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT discord_id, discord_name, character_name, main_class, branch
        FROM game_characters
        """
    )
    db_profiles = {
        int(r["discord_id"]): {key: r[key] for key in r.keys()}
        for r in cursor.fetchall()
    }

    payloads = {}
    if guild is not None:
        for member in guild.members:
            if member.bot:
                continue
            rec = db_profiles.get(member.id, {})
            payloads[member.id] = {
                "discord_id": member.id,
                "discord_name": rec.get("discord_name") or str(member),
                "character_name": rec.get("character_name") or "",
                "main_class": rec.get("main_class") or "",
                "branch": rec.get("branch") or "",
                "joined_at": member.joined_at.strftime("%Y-%m-%d %H:%M:%S")
                if member.joined_at
                else "",
                "joined_at_dt": member.joined_at,
            }
    for did, rec in db_profiles.items():
        payloads.setdefault(
            did,
            {
                "discord_id": did,
                "discord_name": rec.get("discord_name") or "",
                "character_name": rec.get("character_name") or "",
                "main_class": rec.get("main_class") or "",
                "branch": rec.get("branch") or "",
            },
        )

    existing = sheet.get_all_values()
    id_to_row = {}
    for index, row in enumerate(existing[1:], start=2):
        if row and str(row[0]).strip().isdigit():
            id_to_row[int(str(row[0]).strip())] = index

    batch_updates = []
    append_rows = []
    for did, profile in payloads.items():
        values = build_member_sheet_row(profile, cursor=cursor, now=now, days=days)
        if did in id_to_row:
            r = id_to_row[did]
            batch_updates.append({"range": f"A{r}:I{r}", "values": [values]})
        else:
            append_rows.append(values)

    conn.close()

    if batch_updates:
        sheet.batch_update(batch_updates, value_input_option="USER_ENTERED")
    for values in append_rows:
        sheet.append_row(values, value_input_option="USER_ENTERED")

    return len(payloads)
