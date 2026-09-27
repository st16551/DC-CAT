# ==================================================
# 檔案名稱：utils/sheets.py
# 檔案用途：Google 試算表連線（只讀 GOOGLE_CREDENTIALS）與成員狀態欄位同步
# ==================================================

import json
import os
import re
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

from utils.database import get_db_connection

SPREADSHEET_ID = os.getenv(
    "SPREADSHEET_ID", "12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4"
)
MEMBER_SHEET_NAME = os.getenv("MEMBER_SHEET_NAME", "成員名單")
FRIENDS_SHEET_NAME = os.getenv("FRIENDS_SHEET_NAME", "好朋友")
LEAVE_SHEET_NAME = os.getenv("LEAVE_SHEET_NAME", "請假")
ACTIVE_SHEET_NAME = os.getenv("ACTIVE_SHEET_NAME", "活躍")
INACTIVE_SHEET_NAME = os.getenv("INACTIVE_SHEET_NAME", "未活躍")
MEMBER_ROLE_ID = 1527550855631339601
MEMBER_ROLE_NAME = "成員"
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

# 成員名單：圖二 A~E（不含 DC ID）
SHEET_HEADERS = [
    "Discord ID",
    "人員資料",
    "職業",
    "分配分會",
    "入會時間",
]
MEMBER_COL_LETTER = "E"
MEMBER_WIDTH = 5

LEAVE_HEADERS = ["Discord ID", "人員資料", "職業", "分配分會", "請假"]
ACTIVE_HEADERS = ["Discord ID", "人員資料", "職業", "分配分會", "活躍"]
INACTIVE_HEADERS = ["Discord ID", "人員資料", "職業", "分配分會", "未活躍"]

# Discord 分會身分組 ID → 試算表分會
BRANCH_ROLE_IDS = {
    1541087729088200765: "1會",
    1541087803151098079: "2會",
    1541087848298446998: "3會",
}
_BRANCH_TOKEN_MAP = {
    "iii": "3會",
    "3會": "3會",
    "3会": "3會",
    "3": "3會",
    "ii": "2會",
    "2會": "2會",
    "2会": "2會",
    "2": "2會",
    "i": "1會",
    "1會": "1會",
    "1会": "1會",
    "1": "1會",
}
_BRANCH_NAME_RE = re.compile(
    r"escalation\s*(iii|ii|i|[123][會会]?)",
    re.IGNORECASE,
)


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


def match_guild_class_in_name(display_name: str):
    """開頭是職業，或名稱中間含職業（例如 巴哈姆特-聖騎(夏天)）。"""
    found = match_guild_class_prefix(display_name)
    if found:
        return found
    name = display_name or ""
    for prefix in _CLASS_PREFIXES_SORTED:
        if prefix in name:
            return prefix
    return None


def is_guild_formatted_display_name(display_name: str) -> bool:
    return match_guild_class_in_name(display_name) is not None


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
    """用伺服器顯示名稱作為人員資料；職業能從名稱解析就補上。"""
    name = (display_name or "").strip()
    if name:
        profile["sheet_label"] = name
    job = match_guild_class_in_name(name)
    if not job:
        return bool(name)
    if not (profile.get("main_class") or "").strip():
        profile["main_class"] = normalize_class_name(job)
    extracted = ""
    if name.startswith(job):
        extracted = _character_from_display_name(name, job)
    if extracted and not (profile.get("character_name") or "").strip():
        profile["character_name"] = extracted
    return True


def has_member_role(member):
    if member is None:
        return False
    for role in getattr(member, "roles", None) or []:
        if getattr(role, "id", None) == MEMBER_ROLE_ID:
            return True
        if (getattr(role, "name", "") or "").strip() == MEMBER_ROLE_NAME:
            return True
    return False


def is_official_roster_member(member):
    """正式公會成員：同時有「成員」與分會身分組。"""
    return has_member_role(member) and bool(branch_from_member_roles(member))


def branch_from_role_name(role_name: str):
    name = (role_name or "").strip()
    if not name:
        return ""
    compact = re.sub(r"\s+", "", name)
    if compact in ("1會", "1会"):
        return "1會"
    if compact in ("2會", "2会"):
        return "2會"
    if compact in ("3會", "3会"):
        return "3會"
    match = _BRANCH_NAME_RE.search(name)
    if not match:
        return ""
    token = match.group(1).lower().replace("会", "會")
    return _BRANCH_TOKEN_MAP.get(token, "")


def branch_from_member_roles(member):
    """用成員身上的分會身分組對應 1會／2會／3會（Escalation 1會、Escalation II …）。"""
    if member is None:
        return ""
    roles = list(getattr(member, "roles", None) or [])
    found = []
    for role in roles:
        mapped = BRANCH_ROLE_IDS.get(getattr(role, "id", None))
        if mapped:
            found.append(mapped)
            continue
        mapped = branch_from_role_name(getattr(role, "name", "") or "")
        if mapped:
            found.append(mapped)
    for prefer in ("1會", "2會", "3會"):
        if prefer in found:
            return prefer
    return ""


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


def get_spreadsheet():
    return get_gspread_client().open_by_key(SPREADSHEET_ID)


def get_or_create_worksheet(spreadsheet, title, rows=2000, cols=8):
    try:
        return spreadsheet.worksheet(title)
    except Exception:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def get_member_sheet(spreadsheet=None):
    spreadsheet = spreadsheet or get_spreadsheet()
    try:
        return spreadsheet.worksheet(MEMBER_SHEET_NAME)
    except Exception:
        return spreadsheet.sheet1


def get_friends_sheet(spreadsheet=None):
    spreadsheet = spreadsheet or get_spreadsheet()
    return get_or_create_worksheet(spreadsheet, FRIENDS_SHEET_NAME)


def detect_member_layout(headers):
    """相容圖一（含 DC ID）與圖二（職業在 C 欄）。"""
    headers = [_cell_text(h) for h in (headers or [])]
    if "DC ID" in headers or "遊戲角色 ID" in headers:
        return {"id": 0, "label": 1, "character": 2, "job": 3, "branch": 4, "joined": 5}
    if len(headers) >= 4 and headers[3] == "職業":
        return {"id": 0, "label": 1, "character": 2, "job": 3, "branch": 4, "joined": 5}
    return {"id": 0, "label": 1, "character": None, "job": 2, "branch": 3, "joined": 4}


def parse_member_row(row, headers=None):
    layout = detect_member_layout(headers)
    cells = [(c or "").strip() if c is not None else "" for c in (row or [])]

    def at(key):
        index = layout.get(key)
        if index is None or index >= len(cells):
            return ""
        return cells[index]

    label = at("label")
    job = at("job")
    character = at("character")
    if not character and label:
        prefix = match_guild_class_prefix(label)
        if prefix:
            character = _character_from_display_name(label, prefix)
    discord_name = label
    if "(" in label and label.endswith(")"):
        discord_name = label[label.rfind("(") + 1 : -1]
    elif "（" in label and label.endswith("）"):
        discord_name = label[label.rfind("（") + 1 : -1]
    return {
        "discord_id": at("id"),
        "discord_name": discord_name,
        "sheet_label": label,
        "character_name": character,
        "main_class": job,
        "branch": at("branch"),
        "joined_at": at("joined"),
    }


def format_member_display(row):
    """相容機器人寫入版 / 舊公開 CSV 版。"""
    if not row:
        return ""
    parsed = parse_member_row(row)
    if parsed.get("sheet_label"):
        return parsed["sheet_label"]
    cells = [(c or "").strip() for c in row]
    first = cells[0] if cells else ""
    if first.isdigit() and len(cells) >= 4:
        return cells[1] or cells[2] or ""
    return cells[1] if len(cells) > 1 else ""


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
    """分會優先用 Discord 身分組／資料庫；都空時才退回試算表已有內容。"""
    for source in sources:
        text = _cell_text(source)
        if text:
            return text
    return ""


def existing_branch_map(rows):
    """A 欄 Discord ID → 分配分會（相容舊欄位位置）。"""
    mapping = {}
    headers = rows[0] if rows else []
    layout = detect_member_layout(headers)
    branch_idx = layout["branch"]
    for row in rows[1:] if rows else []:
        if not row:
            continue
        discord_id = _cell_text(row[0] if len(row) > 0 else "")
        if not discord_id:
            continue
        branch = _cell_text(row[branch_idx] if len(row) > branch_idx else "")
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


def collect_member_sync_payload(profile: dict, cursor=None, now=None, days=None):
    """組成成員名單列 + 請假／活躍／未活躍文字。"""
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
    member_row = [
        str(discord_id),
        personnel,
        job,
        branch,
        joined,
    ]
    if close_conn:
        cursor.connection.close()
    return {
        "member": member_row,
        "leave": leave_text,
        "active": active_text,
        "inactive": inactive_text,
    }


def build_member_sheet_row(profile: dict, cursor=None, now=None, days=None):
    return collect_member_sync_payload(profile, cursor=cursor, now=now, days=days)[
        "member"
    ]


def _pad_row(values, width=MEMBER_WIDTH):
    row = list(values)[:width]
    while len(row) < width:
        row.append("")
    return row


def _write_named_table(sheet, headers, data_rows):
    width = len(headers)
    matrix = [headers] + [_pad_row(row, width) for row in data_rows]
    end_row = len(matrix)
    sheet.update(f"A1:E{end_row}", matrix, value_input_option="USER_ENTERED")
    leftover = max(sheet.row_count, end_row)
    clears = [f"F1:I{max(leftover, 1)}"]
    if leftover > end_row:
        clears.append(f"A{end_row + 1}:E{leftover}")
    sheet.batch_clear(clears)


def _write_member_table_batch(sheet, data_rows):
    """一次寫入成員名單 A1:E，並清掉舊的 F~I。"""
    _write_named_table(sheet, SHEET_HEADERS, data_rows)


def _write_friends_table_batch(sheet, data_rows):
    _write_named_table(sheet, SHEET_HEADERS, data_rows)


def _write_status_table(sheet, headers, data_rows):
    width = len(headers)
    matrix = [headers] + [_pad_row(row, width) for row in data_rows]
    end_row = len(matrix)
    sheet.update(f"A1:E{end_row}", matrix, value_input_option="USER_ENTERED")
    leftover = max(sheet.row_count, end_row)
    if leftover > end_row:
        sheet.batch_clear([f"A{end_row + 1}:E{leftover}"])


def write_status_tabs(spreadsheet, leave_rows, active_rows, inactive_rows):
    leave_ws = get_or_create_worksheet(spreadsheet, LEAVE_SHEET_NAME)
    active_ws = get_or_create_worksheet(spreadsheet, ACTIVE_SHEET_NAME)
    inactive_ws = get_or_create_worksheet(spreadsheet, INACTIVE_SHEET_NAME)
    _write_status_table(leave_ws, LEAVE_HEADERS, leave_rows)
    _write_status_table(active_ws, ACTIVE_HEADERS, active_rows)
    _write_status_table(inactive_ws, INACTIVE_HEADERS, inactive_rows)


def status_row(member_row, status_text):
    return _pad_row(member_row[:4] + [status_text], 5)


def ensure_sheet_headers(sheet):
    current = sheet.row_values(1)
    if current[: len(SHEET_HEADERS)] != SHEET_HEADERS:
        sheet.update("A1:E1", [SHEET_HEADERS], value_input_option="USER_ENTERED")


def load_sheet_profile(discord_id):
    """依 A 欄 Discord ID 讀回試算表既有列，供修改成員時預填。"""
    try:
        rows = get_member_sheet().get_all_values()
    except Exception:
        return None
    target = str(int(discord_id))
    headers = rows[0] if rows else []
    for row in rows[1:] if rows else []:
        if not row or not str(row[0]).strip().isdigit():
            continue
        if str(int(str(row[0]).strip())) != target:
            continue
        parsed = parse_member_row(row, headers)
        parsed["discord_id"] = int(discord_id)
        return parsed
    return None


def _upsert_one_status_sheet(worksheet, headers, discord_id, row_or_none):
    rows = worksheet.get_all_values()
    data_rows = []
    for row in rows[1:] if rows else []:
        if not row:
            continue
        if str(row[0]).strip() == str(discord_id).strip():
            continue
        data_rows.append(_pad_row(row, 5))
    if row_or_none:
        data_rows.append(_pad_row(row_or_none, 5))
    _write_status_table(worksheet, headers, data_rows)


def upsert_member_sheet_values(values, status=None, spreadsheet=None):
    """更新成員名單 A~E，並連動請假／活躍／未活躍分頁。"""
    spreadsheet = spreadsheet or get_spreadsheet()
    sheet = get_member_sheet(spreadsheet)
    values = _pad_row(values, MEMBER_WIDTH)
    discord_id = str(values[0]).strip()
    rows = sheet.get_all_values()
    values[3] = resolve_branch(
        values[3],
        lookup_sheet_branch(existing_branch_map(rows), discord_id),
    )
    data_rows = [_pad_row(r, MEMBER_WIDTH) for r in rows[1:]] if rows else []
    replaced = False
    for idx, row in enumerate(data_rows):
        if str(row[0]).strip() == discord_id:
            data_rows[idx] = values
            replaced = True
            break
    if not replaced:
        data_rows.append(values)
    _write_member_table_batch(sheet, data_rows)

    if status is not None:
        leave_ws = get_or_create_worksheet(spreadsheet, LEAVE_SHEET_NAME)
        active_ws = get_or_create_worksheet(spreadsheet, ACTIVE_SHEET_NAME)
        inactive_ws = get_or_create_worksheet(spreadsheet, INACTIVE_SHEET_NAME)
        leave_row = status_row(values, status["leave"]) if status.get("leave") else None
        active_row = status_row(values, status["active"]) if status.get("active") else None
        inactive_row = (
            status_row(values, status["inactive"]) if status.get("inactive") else None
        )
        _upsert_one_status_sheet(leave_ws, LEAVE_HEADERS, discord_id, leave_row)
        _upsert_one_status_sheet(active_ws, ACTIVE_HEADERS, discord_id, active_row)
        _upsert_one_status_sheet(inactive_ws, INACTIVE_HEADERS, discord_id, inactive_row)


def _resolve_profile_branch(profile, member, force=False, sheet_branch=""):
    role_branch = branch_from_member_roles(member)
    extra_branch = profile.get("branch")
    if force:
        return resolve_branch(extra_branch, role_branch, sheet_branch)
    return resolve_branch(role_branch, extra_branch, sheet_branch)


def _remove_id_from_rows(rows, discord_id):
    target = str(discord_id).strip()
    kept = []
    for row in rows[1:] if rows else []:
        if not row:
            continue
        if str(row[0]).strip() == target:
            continue
        kept.append(_pad_row(row, MEMBER_WIDTH))
    return kept


def _build_member_profile(member, rec, sheet_branch=""):
    display_name = discord_member_display_name(member) or str(member)
    profile = {
        "discord_id": member.id,
        "discord_name": display_name,
        "character_name": rec.get("character_name") or "",
        "joined_at": member.joined_at.strftime("%Y-%m-%d %H:%M:%S")
        if member.joined_at
        else "",
        "joined_at_dt": member.joined_at,
    }
    apply_display_name_profile(profile, display_name)
    profile["branch"] = resolve_branch(
        branch_from_member_roles(member),
        rec.get("branch"),
        sheet_branch,
    )
    return profile


def _upsert_game_character(cursor, profile):
    cursor.execute(
        """
        INSERT INTO game_characters (
            discord_id, discord_name, game_name, character_name, main_class, branch
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET
            discord_name = excluded.discord_name,
            character_name = excluded.character_name,
            main_class = excluded.main_class,
            branch = CASE
                WHEN excluded.branch IS NULL OR excluded.branch = '' THEN game_characters.branch
                ELSE excluded.branch
            END
        """,
        (
            int(profile["discord_id"]),
            profile.get("discord_name") or "",
            "靈谷",
            profile.get("character_name") or "",
            profile.get("main_class") or "",
            profile.get("branch") or "",
        ),
    )
def _ordered_ids(existing_rows, payloads):
    ordered_ids = []
    seen = set()
    for row in existing_rows[1:] if existing_rows else []:
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
    return ordered_ids


def sync_member_by_discord_id(
    discord_id, member=None, extra_profile=None, days=None, force=False
):
    """依身分組寫入成員名單或好朋友，並連動請假／活躍／未活躍分頁。"""
    display_name = discord_member_display_name(member)
    has_member = has_member_role(member)
    role_branch = branch_from_member_roles(member)
    if not force and not has_member:
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
    extra_branch = profile.get("branch")
    db_branch = ""
    if row:
        profile.setdefault("discord_name", row["discord_name"] or "")
        if not (profile.get("character_name") or "").strip():
            profile["character_name"] = row["character_name"] or ""
        db_branch = row["branch"] or ""
    if member is not None:
        profile["discord_name"] = display_name or str(member)
        if getattr(member, "joined_at", None):
            profile["joined_at_dt"] = member.joined_at
            profile.setdefault(
                "joined_at",
                member.joined_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
    apply_display_name_profile(profile, display_name)
    sheet_branch = ""
    try:
        existing = load_sheet_profile(discord_id) or {}
        sheet_branch = existing.get("branch") or ""
    except Exception:
        sheet_branch = ""
    profile["branch"] = resolve_branch(
        extra_branch if force else None,
        role_branch,
        extra_branch,
        db_branch,
        sheet_branch,
    )
    payload = collect_member_sync_payload(profile, cursor=cursor, days=days)
    _upsert_game_character(cursor, profile)
    conn.commit()
    conn.close()

    official = has_member and bool(role_branch or (force and extra_branch))
    spreadsheet = get_spreadsheet()
    member_sheet = get_member_sheet(spreadsheet)
    friends_sheet = get_friends_sheet(spreadsheet)
    values = payload["member"]
    member_rows = _remove_id_from_rows(member_sheet.get_all_values(), discord_id)
    friend_rows = _remove_id_from_rows(friends_sheet.get_all_values(), discord_id)
    if official:
        member_rows.append(values)
        status = {
            "leave": payload["leave"],
            "active": payload["active"],
            "inactive": payload["inactive"],
        }
    else:
        friend_rows.append(values)
        status = {"leave": "", "active": "", "inactive": ""}
    _write_member_table_batch(member_sheet, member_rows)
    _write_friends_table_batch(friends_sheet, friend_rows)

    leave_ws = get_or_create_worksheet(spreadsheet, LEAVE_SHEET_NAME)
    active_ws = get_or_create_worksheet(spreadsheet, ACTIVE_SHEET_NAME)
    inactive_ws = get_or_create_worksheet(spreadsheet, INACTIVE_SHEET_NAME)
    _upsert_one_status_sheet(
        leave_ws,
        LEAVE_HEADERS,
        discord_id,
        status_row(values, status["leave"]) if status["leave"] else None,
    )
    _upsert_one_status_sheet(
        active_ws,
        ACTIVE_HEADERS,
        discord_id,
        status_row(values, status["active"]) if status["active"] else None,
    )
    _upsert_one_status_sheet(
        inactive_ws,
        INACTIVE_HEADERS,
        discord_id,
        status_row(values, status["inactive"]) if status["inactive"] else None,
    )
    return values


def sync_all_members_to_sheet(guild, days=None):
    """有「成員」+分會 → 成員名單；只有成員沒有分會 → 好朋友。"""
    days = days if days is not None else INACTIVE_DAYS
    now = datetime.now()
    spreadsheet = get_spreadsheet()
    sheet = get_member_sheet(spreadsheet)
    friends_sheet = get_friends_sheet(spreadsheet)

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

    existing_members = sheet.get_all_values()
    existing_friends = friends_sheet.get_all_values()
    sheet_branches = existing_branch_map(existing_members)
    sheet_branches.update(existing_branch_map(existing_friends))

    official = {}
    friends = {}
    if guild is not None:
        for member in guild.members:
            if member.bot:
                continue
            if not has_member_role(member):
                continue
            rec = db_profiles.get(member.id, {})
            profile = _build_member_profile(
                member,
                rec,
                lookup_sheet_branch(sheet_branches, member.id),
            )
            _upsert_game_character(cursor, profile)
            if branch_from_member_roles(member):
                official[member.id] = profile
            else:
                friends[member.id] = profile
    conn.commit()

    member_rows = []
    leave_rows = []
    active_rows = []
    inactive_rows = []
    for did in _ordered_ids(existing_members, official):
        payload = collect_member_sync_payload(
            official[did], cursor=cursor, now=now, days=days
        )
        member_rows.append(payload["member"])
        if payload["leave"]:
            leave_rows.append(status_row(payload["member"], payload["leave"]))
        if payload["active"]:
            active_rows.append(status_row(payload["member"], payload["active"]))
        if payload["inactive"]:
            inactive_rows.append(status_row(payload["member"], payload["inactive"]))

    friend_rows = []
    for did in _ordered_ids(existing_friends, friends):
        payload = collect_member_sync_payload(
            friends[did], cursor=cursor, now=now, days=days
        )
        friend_rows.append(payload["member"])
    conn.close()

    _write_member_table_batch(sheet, member_rows)
    _write_friends_table_batch(friends_sheet, friend_rows)
    write_status_tabs(spreadsheet, leave_rows, active_rows, inactive_rows)
    return {"members": len(official), "friends": len(friends)}
