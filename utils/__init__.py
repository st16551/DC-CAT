from .database import (
    DATA_FILE,
    DB_FILE,
    ECONOMY_DB_FILE,
    JSON_DB_PATH,
    get_db_connection,
    init_db,
    load_data,
    save_json_data,
)
from .economy_helper import (
    get_wallet_balance,
    modify_balance,
    update_user_coins,
)
from .level_helper import add_user_xp

CUSTOM_CONFIG_FILE = "config.json"

_store = load_data()
if not isinstance(_store, dict):
    _store = {}

activity_data = _store.setdefault("activity_data", {})
if not isinstance(activity_data, dict):
    activity_data = {}
    _store["activity_data"] = activity_data

custom_configs = _store.setdefault("custom_raid_configs", {})
if not isinstance(custom_configs, dict):
    custom_configs = {}
    _store["custom_raid_configs"] = custom_configs

temp_voice_rooms = {}


def save_data(data_or_file=None, data=None):
    """相容舊模組的多種寫法：save_data()、save_data(dict)、save_data(檔名, dict)。"""
    if data is not None:
        _store["custom_raid_configs"] = data
        save_json_data(_store)
        return

    if data_or_file is None:
        _store["activity_data"] = activity_data
        _store["custom_raid_configs"] = custom_configs
        save_json_data(_store)
        return

    if data_or_file is activity_data:
        _store["activity_data"] = activity_data
        save_json_data(_store)
        return

    if data_or_file is custom_configs:
        _store["custom_raid_configs"] = custom_configs
        save_json_data(_store)
        return

    if isinstance(data_or_file, dict):
        _store.update(data_or_file)
        save_json_data(_store)
        return

    save_json_data(_store)


__all__ = [
    "DATA_FILE",
    "DB_FILE",
    "ECONOMY_DB_FILE",
    "JSON_DB_PATH",
    "CUSTOM_CONFIG_FILE",
    "activity_data",
    "custom_configs",
    "temp_voice_rooms",
    "get_db_connection",
    "init_db",
    "load_data",
    "save_data",
    "get_wallet_balance",
    "modify_balance",
    "update_user_coins",
    "add_user_xp",
]
