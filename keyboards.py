from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def channel_kb(channel_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Перейти в канал мероприятия", url=channel_link)]
    ])


def upsell_kb(url: str, text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, url=url)]
    ])


def referral_share_kb(ref_link: str) -> InlineKeyboardMarkup:
    share_text = "Залетай на AI-интенсив 20-21 августа 🔥"
    tg_share_url = f"https://t.me/share/url?url={quote(ref_link, safe='')}&text={quote(share_text, safe='')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться с другом", url=tg_share_url)]
    ])


def unknown_tariff_kb(site_link: str, support_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Выбрать тариф на сайте", url=site_link)],
        [InlineKeyboardButton(text="💬 Написать в поддержку", url=support_link)],
    ])
