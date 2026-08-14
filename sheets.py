"""
Работа с Google Sheets как базой подписчиков.

Структура листа "Users" (создаётся автоматически при первом запуске, если её нет):
telegram_id | username | full_name | tariff | joined_at | ref_code | referred_by | referrals_count | rewards_given | can_broadcast

Требуется:
1. Создать проект в Google Cloud, включить Google Sheets API.
2. Создать сервисный аккаунт, скачать JSON-ключ.
3. Расшарить таблицу (Google Sheet) на email сервисного аккаунта с правами Редактора.
4. В .env указать GOOGLE_SHEET_ID (id из URL таблицы) и GOOGLE_SERVICE_ACCOUNT_JSON
   (путь к json-файлу ключа, либо весь JSON одной строкой).
"""

import json
import os
import datetime as dt
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

USERS_HEADER = [
    "telegram_id", "username", "full_name", "tariff", "joined_at",
    "ref_code", "referred_by", "referrals_count", "rewards_given", "can_broadcast",
]

_client = None
_sheet = None
_ws_users = None


def _get_credentials():
    raw = GOOGLE_SERVICE_ACCOUNT_JSON
    if raw and os.path.exists(raw):
        return Credentials.from_service_account_file(raw, scopes=SCOPES)
    # иначе считаем, что в переменной лежит сырой JSON
    info = json.loads(raw)
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def init_sheets():
    global _client, _sheet, _ws_users
    creds = _get_credentials()
    _client = gspread.authorize(creds)
    _sheet = _client.open_by_key(GOOGLE_SHEET_ID)

    try:
        _ws_users = _sheet.worksheet("Users")
    except gspread.WorksheetNotFound:
        _ws_users = _sheet.add_worksheet(title="Users", rows=2000, cols=len(USERS_HEADER))
        _ws_users.append_row(USERS_HEADER)
        return

    # если лист пустой — добавим заголовок
    if not _ws_users.get_all_values():
        _ws_users.append_row(USERS_HEADER)


def _find_row_by_id(telegram_id: int) -> Optional[int]:
    """Возвращает номер строки (1-indexed, с учётом заголовка) или None."""
    ids = _ws_users.col_values(1)  # первая колонка = telegram_id
    tid = str(telegram_id)
    for i, val in enumerate(ids, start=1):
        if val == tid:
            return i
    return None


def get_user(telegram_id: int) -> Optional[dict]:
    row_num = _find_row_by_id(telegram_id)
    if row_num is None:
        return None
    row = _ws_users.row_values(row_num)
    row += [""] * (len(USERS_HEADER) - len(row))
    return dict(zip(USERS_HEADER, row))


def upsert_user(telegram_id: int, username: str, full_name: str, tariff: str,
                 referred_by: Optional[str] = None) -> str:
    """Создаёт пользователя, если его нет, либо обновляет тариф. Возвращает его личный ref_code."""
    existing = get_user(telegram_id)
    ref_code = f"ref_{telegram_id}"

    if existing:
        row_num = _find_row_by_id(telegram_id)
        # обновляем тариф, если поменялся (например, был free, стал vip)
        if existing.get("tariff") != tariff:
            _ws_users.update_cell(row_num, USERS_HEADER.index("tariff") + 1, tariff)
        return existing.get("ref_code") or ref_code

    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        str(telegram_id), username or "", full_name or "", tariff, now,
        ref_code, referred_by or "", "0", "", "TRUE",
    ]
    _ws_users.append_row(row)

    if referred_by:
        _increment_referrals(referred_by)

    return ref_code


def _increment_referrals(ref_code: str) -> Optional[int]:
    """Находит владельца ref_code и увеличивает его счётчик рефералов. Возвращает новое значение."""
    codes = _ws_users.col_values(USERS_HEADER.index("ref_code") + 1)
    for i, val in enumerate(codes, start=1):
        if val == ref_code:
            count_col = USERS_HEADER.index("referrals_count") + 1
            current = _ws_users.cell(i, count_col).value
            new_count = int(current or 0) + 1
            _ws_users.update_cell(i, count_col, new_count)
            return new_count
    return None


def get_referrer_telegram_id(ref_code: str) -> Optional[int]:
    if not ref_code or not ref_code.startswith("ref_"):
        return None
    try:
        return int(ref_code.replace("ref_", "", 1))
    except ValueError:
        return None


def get_referrals_count(telegram_id: int) -> int:
    user = get_user(telegram_id)
    if not user:
        return 0
    return int(user.get("referrals_count") or 0)


def mark_reward_given(telegram_id: int, tier_count: int):
    row_num = _find_row_by_id(telegram_id)
    if row_num is None:
        return
    col = USERS_HEADER.index("rewards_given") + 1
    current = _ws_users.cell(row_num, col).value or ""
    given = set(x for x in current.split(",") if x)
    given.add(str(tier_count))
    _ws_users.update_cell(row_num, col, ",".join(sorted(given, key=int)))


def get_reward_tiers_given(telegram_id: int) -> set:
    user = get_user(telegram_id)
    if not user:
        return set()
    current = user.get("rewards_given") or ""
    return set(x for x in current.split(",") if x)


def get_all_broadcast_ids() -> list[int]:
    """Список telegram_id всех, кому можно слать рассылку (для команды /broadcast)."""
    ids_col = _ws_users.col_values(1)[1:]  # без заголовка
    flags_col = _ws_users.col_values(USERS_HEADER.index("can_broadcast") + 1)[1:]
    result = []
    for tid, flag in zip(ids_col, flags_col):
        if tid and flag.strip().upper() != "FALSE":
            try:
                result.append(int(tid))
            except ValueError:
                pass
    return result
