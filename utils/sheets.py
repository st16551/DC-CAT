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
    "狂戰士": "戰士",
    "2會": "2会",
    "3會": "3会",
}

# 公會暱稱開頭職業（長的放前面，避免「聖騎」搶先吃掉「聖騎士」）
GUILD_CLASS_PREFIXES = (
    "聖騎士",
    "狂戰士",
    "聖騎",
    "戰士",
    "法師",
    "死靈",
    "牧師",
    "槍手",
    "忍者",
    "編織",
)
_CLASS_PREFIXES_SORTED = tuple(
    sorted(GUILD_CLASS_PREFIXES, key=len, reverse=True)
)
_CLASS_SEPARATORS = "-－—_"

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


def match_guild_class_prefix(display_name: str):
    """顯示名稱開頭是否為公會職業（職業-角色 或僅職業）。不符合則回傳 None。"""
    name = (display_name or "").strip()
    if not name:
        return None
    for prefix in _CLASS_PREFIXES_SORTED:
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        if rest == "" or rest[0] in _CLASS_SEPARATORS:
            return prefix
    return None


def is_guild_formatted_display_name(display_name: str) -> bool:
    return match_guild_class_prefix(display_name) is not None


def discord_member_display_name(member) -> str:
    if member is None:
        return ""
    return (getattr(member, "display_name", None) or "").strip()


def _character_from_display_name(display_name: str, job: str) -> str:
    rest = (display_name or "")[len(job) :].lstrip(_CLASS_SEPARATORS).strip()
    for mark in ("(", "（", "[", "【"):
        if mark in rest:
            rest = rest.split(mark, 1)[0]
            break
    return rest.strip()


def apply_display_name_profile(profile: dict, display_name: str) -> bool:
    """用伺服器顯示名稱補上職業／人員資料；已有明確欄位則不覆蓋。"""
    job = match_guild_class_prefix(display_name)
    if not job:
        return False
    profile["sheet_label"] = display_name.strip()
    if not (profile.get("main_class") or "").strip():
        profile["main_class"] = normalize_class_name(job)
    extracted = _character_from_display_name(display_name.strip(), job)
    if extracted and not (profile.get("character_name") or "").strip():
        profile["character_name"] = extracted
    return True


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


def _cell_text(value):
    return (str(value) if value is not None else "").strip()


def resolve_branch(*sources):
    """分會優先用資料庫；都空時才退回試算表 E 欄已有內容。"""
    for source in sources:
        text = _cell_text(source)
        if text:
            return text
    return ""


def existing_branch_map(rows):
    """A 欄 Discord ID → E 欄（分配分會）手動／既有內容。"""
    mapping = {}
    for row in rows[1:] if rows else []:
        if not row:
            continue
        discord_id = _cell_text(row[0] if len(row) > 0 else "")
        if not discord_id:
            continue
        branch = _cell_text(row[4] if len(row) > 4 else "")
        if not branch:
            continue
        mapping[discord_id] = branch
        if discord_id.isdigit():
            mapping[str(int(discord_id))] = branch
    return mapping


def lookup_sheet_branch(branch_map, discord_id):
    key = _cell_text(discord_id)
    if key in branch_map:
        return branch_map[key]
    if key.isdigit():
        return branch_map.get(str(int(key)), "")
    return ""


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
    branch = resolve_branch(profile.get("branch"))
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
    personnel = (profile.get("sheet_label") or "").strip() or build_personnel_label(
        job, character_name, discord_name, discord_id
    )
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


def _pad_row(values, width=9):
    row = list(values)[:width]
    while len(row) < width:
        row.append("")
    return row


def _write_member_table_batch(sheet, data_rows):
    """一次寫入整張成員表 A1:I（含表頭），避免逐列 append 觸發 429。"""
    matrix = [SHEET_HEADERS] + [_pad_row(row) for row in data_rows]
    end_row = len(matrix)
    sheet.update(f"A1:I{end_row}", matrix, value_input_option="USER_ENTERED")
    leftover = max(sheet.row_count, end_row)
    if leftover > end_row:
        sheet.batch_clear([f"A{end_row + 1}:I{leftover}"])


def ensure_sheet_headers(sheet):
    current = sheet.row_values(1)
    if current[: len(SHEET_HEADERS)] != SHEET_HEADERS:
        sheet.update("A1:I1", [SHEET_HEADERS], value_input_option="USER_ENTERED")


def load_sheet_profile(discord_id):
    """依 A 欄 Discord ID 讀回試算表既有列，供修改成員時預填。"""
    try:
        rows = get_member_sheet().get_all_values()
    except Exception:
        return None
    target = str(int(discord_id))
    for row in rows[1:] if rows else []:
        if not row or not str(row[0]).strip().isdigit():
            continue
        if str(int(str(row[0]).strip())) != target:
            continue
        padded = _pad_row(row)
        return {
            "discord_id": int(discord_id),
            "discord_name": (padded[1] or "").strip(),
            "character_name": (padded[2] or "").strip(),
            "main_class": (padded[3] or "").strip(),
            "branch": (padded[4] or "").strip(),
            "sheet_label": (padded[1] or "").strip(),
        }
    return None


def upsert_member_sheet_values(values):
    """用 A 欄 Discord ID 更新或新增一列；單筆也走一次 range update，不用 append_row。"""
    sheet = get_member_sheet()
    values = _pad_row(values)
    discord_id = str(values[0]).strip()
    rows = sheet.get_all_values()
    values[4] = resolve_branch(
        values[4],
        lookup_sheet_branch(existing_branch_map(rows), discord_id),
    )
    if not rows or rows[0][: len(SHEET_HEADERS)] != SHEET_HEADERS:
        data_rows = [_pad_row(r) for r in rows[1:]] if rows else []
        replaced = False
        for idx, row in enumerate(data_rows):
            if str(row[0]).strip() == discord_id:
                data_rows[idx] = values
                replaced = True
                break
        if not replaced:
            data_rows.append(values)
        _write_member_table_batch(sheet, data_rows)
        return

    target_row = None
    for index, row in enumerate(rows[1:], start=2):
        if row and str(row[0]).strip() == discord_id:
            target_row = index
            break
    if target_row:
        sheet.update(f"A{target_row}:I{target_row}", [values], value_input_option="USER_ENTERED")
        return
    next_row = max(len(rows) + 1, 2)
    sheet.update(f"A{next_row}:I{next_row}", [values], value_input_option="USER_ENTERED")


def sync_member_by_discord_id(
    discord_id, member=None, extra_profile=None, days=None, force=False
):
    """把單一成員寫進試算表。force=True 時（幹部修改）即使暱稱格式不符也會寫入。"""
    display_name = discord_member_display_name(member)
    if not force and not is_guild_formatted_display_name(display_name):
        return None

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
    db_branch = ""
    extra_branch = profile.get("branch")
    if row:
        profile.setdefault("discord_name", row["discord_name"] or "")
        if not (profile.get("character_name") or "").strip():
            profile["character_name"] = row["character_name"] or ""
        db_branch = row["branch"] or ""
    # 幹部明確送出的分會優先於舊的資料庫／試算表值
    profile["branch"] = resolve_branch(extra_branch, db_branch)
    if member is not None:
        profile["discord_name"] = display_name or str(member)
        if getattr(member, "joined_at", None):
            profile["joined_at_dt"] = member.joined_at
            profile.setdefault(
                "joined_at",
                member.joined_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
    if is_guild_formatted_display_name(display_name):
        apply_display_name_profile(profile, display_name)
    values = build_member_sheet_row(profile, cursor=cursor, days=days)
    conn.close()
    upsert_member_sheet_values(values)
    return values


def sync_all_members_to_sheet(guild, days=None):
    """只同步 Discord 顯示名稱符合公會職業格式的成員，一次寫回試算表。"""
    days = days if days is not None else INACTIVE_DAYS
    now = datetime.now()
    sheet = get_member_sheet()

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

    existing = sheet.get_all_values()
    sheet_branches = existing_branch_map(existing)

    payloads = {}
    if guild is not None:
        for member in guild.members:
            if member.bot:
                continue
            display_name = discord_member_display_name(member)
            if not is_guild_formatted_display_name(display_name):
                continue
            rec = db_profiles.get(member.id, {})
            profile = {
                "discord_id": member.id,
                "discord_name": display_name,
                "character_name": rec.get("character_name") or "",
                "branch": resolve_branch(
                    rec.get("branch"),
                    lookup_sheet_branch(sheet_branches, member.id),
                ),
                "joined_at": member.joined_at.strftime("%Y-%m-%d %H:%M:%S")
                if member.joined_at
                else "",
                "joined_at_dt": member.joined_at,
            }
            apply_display_name_profile(profile, display_name)
            payloads[member.id] = profile
    ordered_ids = []
    seen = set()
    for row in existing[1:]:
        if not row or not str(row[0]).strip().isdigit():
            continue
        did = int(str(row[0]).strip())
        if did in payloads and did not in seen:
            ordered_ids.append(did)
            seen.add(did)
    for did in payloads:
        if did not in seen:
            ordered_ids.append(did)
            seen.add(did)

    data_rows = [
        build_member_sheet_row(payloads[did], cursor=cursor, now=now, days=days)
        for did in ordered_ids
    ]
    conn.close()

    _write_member_table_batch(sheet, data_rows)
    return len(payloads)
