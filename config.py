import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ID/юзернейм КАНАЛА МЕРОПРИЯТИЯ для бесплатного тарифа
EVENT_CHANNEL_ID = os.getenv("EVENT_CHANNEL_ID")          # числовой ID канала (например -1001234567890), нужен только если хочешь одноразовые инвайт-ссылки через API
EVENT_CHANNEL_INVITE = os.getenv("EVENT_CHANNEL_INVITE")  # обычная (постоянная) ссылка-приглашение на канал для бесплатного тарифа

# Отдельный VIP-канал — сюда попадают те, кто оплатил VIP
VIP_CHANNEL_ID = os.getenv("VIP_CHANNEL_ID")               # числовой ID VIP-канала, опционально (для одноразовых ссылок через API)
VIP_CHANNEL_INVITE = os.getenv("VIP_CHANNEL_INVITE")       # постоянная ссылка-приглашение в VIP-канал

# --- Google Sheets ---
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")  # путь к файлу или сырой JSON в переменной

# --- Тарифы ---
TARIFF_FREE = "free"
TARIFF_VIP = "vip"

TARIFF_NAMES = {
    TARIFF_FREE: "Бесплатный",
    TARIFF_VIP: "VIP (490 ₽)",
}

# --- Апсейл: ссылка/цена на флагманский курс для VIP-допродажи ---
FLAGSHIP_COURSE_LINK = os.getenv("FLAGSHIP_COURSE_LINK", "https://example.com/flagship")
VIP_UPGRADE_LINK = os.getenv("VIP_UPGRADE_LINK", "https://example.com/vip")

# --- Реферальная программа: пороги и бонусы ---
REFERRAL_TIERS = [
    {"count": 1, "reward": "Гайд «5 AI-инструментов для быстрого старта» (PDF)"},
    {"count": 3, "reward": "Доступ к записи VIP-дня интенсива + разбор от эксперта"},
    {"count": 5, "reward": "Бесплатная 30-минутная консультация по AI-нише"},
    {"count": 10, "reward": "Бесплатное место в следующем потоке школы «ИИ на простом»"},
]
