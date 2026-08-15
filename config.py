import os
from dotenv import load_dotenv

load_dotenv()


def _parse_chat_id(value: str | None):
    """
    Числовой ID канала (например -1001234567890) превращаем в int,
    чтобы aiogram точно его принял. Если это @username канала — оставляем строкой.
    Если переменная не задана — возвращаем None.
    """
    if not value:
        return None
    value = value.strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value


# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Приватный канал/группа-журнал: сюда бот дублирует каждое событие воронки
# (дошёл до бота, выбрал тариф, привёл друга и т.д.), не завися от Google Таблицы.
# Добавь бота туда админом и укажи числовой ID канала (например -1001234567890).
ADMIN_LOG_CHAT_ID = _parse_chat_id(os.getenv("ADMIN_LOG_CHAT_ID"))

# ID/юзернейм КАНАЛА МЕРОПРИЯТИЯ для тарифа Стандарт
EVENT_CHANNEL_ID = _parse_chat_id(os.getenv("EVENT_CHANNEL_ID"))          # числовой ID канала, нужен только если хочешь одноразовые инвайт-ссылки через API
EVENT_CHANNEL_INVITE = os.getenv("EVENT_CHANNEL_INVITE")                  # обычная (постоянная) ссылка-приглашение на канал для тарифа Стандарт

# Отдельный VIP-канал: сюда попадают те, кто оплатил VIP
VIP_CHANNEL_ID = _parse_chat_id(os.getenv("VIP_CHANNEL_ID"))              # числовой ID VIP-канала, опционально (для одноразовых ссылок через API)
VIP_CHANNEL_INVITE = os.getenv("VIP_CHANNEL_INVITE")                      # постоянная ссылка-приглашение в VIP-канал

# --- Google Sheets ---
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")  # путь к файлу или сырой JSON в переменной

# --- Тарифы ---
TARIFF_FREE = "free"
TARIFF_VIP = "vip"

TARIFF_NAMES = {
    TARIFF_FREE: "Стандарт",
    TARIFF_VIP: "VIP",
}

# --- Апсейл: ссылка/цена на флагманский курс для VIP-допродажи ---
FLAGSHIP_COURSE_LINK = os.getenv("FLAGSHIP_COURSE_LINK", "https://example.com/flagship")
VIP_UPGRADE_LINK = os.getenv("VIP_UPGRADE_LINK", "https://example.com/vip")

# --- Сайт интенсива и поддержка: используются в сообщении, когда бот не видит тариф ---
INTENSIVE_SITE_LINK = os.getenv("INTENSIVE_SITE_LINK", "https://olgapuzanova0311-art.github.io/zarabotok/")
SUPPORT_CONTACT_LINK = os.getenv("SUPPORT_CONTACT_LINK", "https://t.me/puzanovateam")

# --- Реферальная программа: пороги и бонусы ---
REFERRAL_TIERS = [
    {"count": 1, "reward": "Гайд «5 AI-инструментов для быстрого старта» (PDF)"},
    {"count": 3, "reward": "Доступ к записи VIP-дня интенсива + разбор от эксперта"},
    {"count": 5, "reward": "Бесплатная 30-минутная консультация по AI-нише"},
    {"count": 10, "reward": "Бесплатное место в следующем потоке школы «ИИ на простом»"},
]
