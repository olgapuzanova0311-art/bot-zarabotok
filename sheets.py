"""
Модуль работы с Google Sheets.

Хранит всех пользователей бота на листе "Users" таблицы GOOGLE_SHEET_ID.
Реферальный код всегда имеет вид "ref_<telegram_id>" — поэтому определить,
кто пригласил (get_referrer_telegram_id), можно локально, без обращения к
таблице: это просто разбор строки. Таблица нужна только для истории,
счётчика рефералов, отметок о выданных бонусах и рассылки.

Колонки на листе "Users" (создаются автоматически при первом запуске):
telegram_id | username | full_name | tariff | ref_code | referred_by | reward_tiers_given | created_at
"""

import json
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

import config

log = logging.getLogger("sheets")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_NAME = "Users"
HEADERS = [
    "telegram_id",
    "username",
    "full_name",
    "tariff",
    "ref_code",
    "referred_by",
    "reward_tiers_given",
    "created_at",
]

COL_TELEGRAM_ID = 1
COL_USERNAME = 2
COL_FULL_NAME = 3
COL_TARIFF = 4
COL_REF_CODE = 5
COL_REFERRED_BY = 6
COL_REWARD_TIERS_GIVEN = 7
COL_CREATED_AT = 8

_client = None
_sheet = None


def _load_credentials() -> Credentials:
    """
    GOOGLE_SERVICE_ACCOUNT_JSON может быть либо путём к файлу, либо самим JSON
    (вставленным одной строкой в переменную окружения на Railway).
    """
    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON не задан")

    raw = raw.strip()
    if raw.startswith("{"):
        info = json.loads(raw)
    else:
        with open(raw, "r", encoding="utf-8") as f:
            info = json.load(f)

    return Credentials.from_service_account_info(info, scopes=SCOPES)


def init_sheets():
    """
    Подключается к Google Sheets и гарантирует наличие листа "Users" с шапкой.
    Бросает исключение, если что-то не так (перехватывается в bot.py -> main()).
    """
    global _client, _sheet

    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID не задан")

    creds = _load_credentials()
    _client = gspread.authorize(creds)

    try:
        spreadsheet = _client.open_by_key(config.GOOGLE_SHEET_ID)
    except gspread.exceptions.SpreadsheetNotFound:
        raise RuntimeError(
            f"Таблица с ID '{config.GOOGLE_SHEET_ID}' не найдена сервисным аккаунтом "
            f"({creds.service_account_email}). Либо GOOGLE_SHEET_ID указан неверно, "
            f"либо таблица не расшарена на этот email с правами Редактор."
        )
    except gspread.exceptions.APIError as e:
        raise RuntimeError(
            f"Google Sheets API вернул ошибку при открытии таблицы: {e}. "
            f"Проверь, что Google Sheets API и Google Drive API включены в проекте "
            f"сервисного аккаунта в Google Cloud Console."
        )

    try:
        _sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        _sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        _sheet.append_row(HEADERS)
        return

    first_row = _sheet.row_values(1)
    if first_row != HEADERS:
        if not first_row:
            _sheet.append_row(HEADERS)
        else:
            log.warning(
                "Шапка листа 'Users' не совпадает с ожидаемой. "
                "Проверь вручную первую строку таблицы."
            )


def _ref_code(telegram_id: int) -> str:
    return f"ref_{telegram_id}"


def get_referrer_telegram_id(ref_code):
    """
    Чисто локальный разбор: ref_code всегда имеет вид 'ref_<telegram_id>'.
    Обращение к таблице не требуется.
    """
    if not ref_code:
        return None
    try:
        prefix = "ref_"
        idx = ref_code.index(prefix)
        return int(ref_code[idx + len(prefix):])
    except (ValueError, AttributeError):
        return None


def _find_row_by_telegram_id(telegram_id: int):
    """Возвращает (номер_строки, значения_строки) или (None, None)."""
    cell = None
    try:
        cell = _sheet.find(str(telegram_id), in_column=COL_TELEGRAM_ID)
    except gspread.exceptions.CellNotFound:
        return None, None
    row_values = _sheet.row_values(cell.row)
    return cell.row, row_values


def upsert_user(telegram_id: int, username: str, full_name: str, tariff: str, referred_by=None) -> str:
    """
    Создаёт пользователя, если его ещё нет, либо обновляет тариф/имя, если он уже есть
    (например, повторно перешёл по ссылке). Возвращает его персональный ref_code.
    """
    ref_code = _ref_code(telegram_id)
    row_num, row_values = _find_row_by_telegram_id(telegram_id)

    if row_num:
        # Пользователь уже есть — обновим username/full_name/tariff, но не затираем
        # referred_by, если он уже был проставлен раньше.
        existing_referred_by = row_values[COL_REFERRED_BY - 1] if len(row_values) >= COL_REFERRED_BY else ""
        _sheet.update(
            f"A{row_num}:H{row_num}",
            [[
                str(telegram_id),
                username,
                full_name,
                tariff,
                ref_code,
                existing_referred_by or (referred_by or ""),
                row_values[COL_REWARD_TIERS_GIVEN - 1] if len(row_values) >= COL_REWARD_TIERS_GIVEN else "",
                row_values[COL_CREATED_AT - 1] if len(row_values) >= COL_CREATED_AT else "",
            ]],
        )
        return ref_code

    _sheet.append_row([
        str(telegram_id),
        username,
        full_name,
        tariff,
        ref_code,
        referred_by or "",
        "",
        datetime.now(timezone.utc).isoformat(),
    ])
    return ref_code


def get_user(telegram_id: int):
    row_num, row_values = _find_row_by_telegram_id(telegram_id)
    if not row_num:
        return None
    padded = row_values + [""] * (len(HEADERS) - len(row_values))
    return {
        "telegram_id": padded[COL_TELEGRAM_ID - 1],
        "username": padded[COL_USERNAME - 1],
        "full_name": padded[COL_FULL_NAME - 1],
        "tariff": padded[COL_TARIFF - 1],
        "ref_code": padded[COL_REF_CODE - 1],
        "referred_by": padded[COL_REFERRED_BY - 1],
        "reward_tiers_given": padded[COL_REWARD_TIERS_GIVEN - 1],
    }


def get_referrals_count(referrer_telegram_id: int) -> int:
    ref_code = _ref_code(referrer_telegram_id)
    all_values = _sheet.get_all_values()[1:]  # без шапки
    return sum(1 for row in all_values if len(row) >= COL_REFERRED_BY and row[COL_REFERRED_BY - 1] == ref_code)


def get_reward_tiers_given(referrer_telegram_id: int) -> str:
    row_num, row_values = _find_row_by_telegram_id(referrer_telegram_id)
    if not row_num or len(row_values) < COL_REWARD_TIERS_GIVEN:
        return ""
    return row_values[COL_REWARD_TIERS_GIVEN - 1] or ""


def mark_reward_given(referrer_telegram_id: int, tier_count: int):
    row_num, row_values = _find_row_by_telegram_id(referrer_telegram_id)
    if not row_num:
        return
    given = row_values[COL_REWARD_TIERS_GIVEN - 1] if len(row_values) >= COL_REWARD_TIERS_GIVEN else ""
    given_list = [g for g in given.split(",") if g]
    if str(tier_count) not in given_list:
        given_list.append(str(tier_count))
    _sheet.update_cell(row_num, COL_REWARD_TIERS_GIVEN, ",".join(given_list))


def get_all_broadcast_ids():
    all_values = _sheet.get_all_values()[1:]  # без шапки
    ids = []
    for row in all_values:
        if row and row[COL_TELEGRAM_ID - 1].strip().isdigit():
            ids.append(int(row[COL_TELEGRAM_ID - 1]))
    return ids
