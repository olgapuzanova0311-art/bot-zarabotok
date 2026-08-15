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
    share_text = "Залетай на AI-интенсив 15-16 августа 🔥"
    tg_share_url = f"https://t.me/share/url?url={ref_link}&text={share_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться с другом", url=tg_share_url)]
    ])
