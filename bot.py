"""
Бот интенсива "AI-старт".

Что делает:
1. Принимает и бесплатных, и VIP-участников после оплаты (переход по диплинку вида
   https://t.me/<bot_username>?start=free   или   ?start=vip
   Ссылки с этими параметрами нужно поставить на кнопки "спасибо за оплату" / после формы GetCourse.
2. Сразу выдаёт ссылку на канал мероприятия.
3. Пишет каждого пользователя в Google Sheets (база для будущих рассылок).
4. Выдаёт каждому персональную реферальную ссылку и начисляет бонусы за приведённых друзей.
5. Через время присылает апсейл: тем, кто на Стандарте, апгрейд на VIP, а VIP-участникам на флагманский курс.
6. /broadcast <текст>: рассылка по всей базе (только для админов).

Деплой: см. README.md
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import sheets
import texts
from keyboards import channel_kb, upsell_kb, referral_share_kb, unknown_tariff_kb

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Если Google Sheets не настроены (или временно недоступны), бот не должен падать
# целиком и переставать отвечать людям, просто пропускаем запись в таблицу.
SHEETS_READY = False


def local_ref_code(telegram_id: int) -> str:
    """Реферальный код без обращения к таблице, используется, если Sheets недоступны."""
    return f"ref_{telegram_id}"


def safe_upsert_user(**kwargs) -> str:
    if not SHEETS_READY:
        return local_ref_code(kwargs["telegram_id"])
    try:
        return sheets.upsert_user(**kwargs)
    except Exception as e:
        log.error(f"Ошибка записи в Google Sheets (upsert_user): {e}")
        return local_ref_code(kwargs["telegram_id"])


def safe_get_referrer_id(ref_code):
    # get_referrer_telegram_id — чисто локальный разбор ref_code (ref_<id>),
    # к таблице не обращается, поэтому Sheets тут не нужны в принципе.
    try:
        return sheets.get_referrer_telegram_id(ref_code)
    except Exception as e:
        log.error(f"Ошибка разбора ref_code (get_referrer_telegram_id): {e}")
        return None


async def log_to_admin_channel(text: str):
    """
    Дублирует событие в приватный канал-журнал (ADMIN_LOG_CHAT_ID), полностью независимо
    от Google Таблицы. Так даже если Sheets не подгрузились, ни один человек не потеряется:
    ты увидишь его в канале в любом случае. Если канал не настроен, просто логирует ошибку
    и не мешает остальной работе бота.
    """
    if not config.ADMIN_LOG_CHAT_ID:
        return
    try:
        await bot.send_message(config.ADMIN_LOG_CHAT_ID, text)
    except Exception as e:
        log.error(f"Не удалось отправить в канал-журнал: {e}")


# ---------- вспомогательные функции ----------

async def get_channel_invite_link(tariff: str) -> str:
    """
    Возвращает ссылку на нужный канал в зависимости от тарифа:
    - free -> канал мероприятия (EVENT_CHANNEL_*)
    - vip  -> отдельный VIP-канал (VIP_CHANNEL_*)
    Если указан числовой ID канала, пробуем создать одноразовую ссылку через API.
    Если не получилось (или ID не указан), используем постоянную ссылку-приглашение.
    """
    if tariff == config.TARIFF_VIP:
        channel_id = config.VIP_CHANNEL_ID
        fallback = config.VIP_CHANNEL_INVITE
    else:
        channel_id = config.EVENT_CHANNEL_ID
        fallback = config.EVENT_CHANNEL_INVITE

    if channel_id:
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=channel_id,
                name="intensive_bot",
                member_limit=1,
            )
            return invite.invite_link
        except Exception as e:
            log.warning(f"Не удалось создать invite link через API для {tariff}: {e}")

    return fallback or "https://t.me/"


def parse_start_payload(payload: str) -> tuple[str | None, str | None]:
    """
    Разбирает параметр диплинка.
    Форматы: 'free', 'vip', 'free_ref_123456', 'vip_ref_123456'
    Возвращает (tariff, ref_code)
    """
    if not payload:
        return None, None
    tariff = None
    ref_code = None
    if payload.startswith("vip"):
        tariff = config.TARIFF_VIP
    elif payload.startswith("free"):
        tariff = config.TARIFF_FREE

    if "ref_" in payload:
        idx = payload.index("ref_")
        ref_code = payload[idx:]

    return tariff, ref_code


async def check_and_reward_referrer(referrer_id: int):
    """Проверяет пороги реферальной программы и уведомляет о новом бонусе."""
    if not SHEETS_READY:
        return
    try:
        count = sheets.get_referrals_count(referrer_id)
        given = sheets.get_reward_tiers_given(referrer_id)
    except Exception as e:
        log.error(f"Ошибка чтения Google Sheets (check_and_reward_referrer): {e}")
        return

    for tier in config.REFERRAL_TIERS:
        if count >= tier["count"] and str(tier["count"]) not in given:
            try:
                sheets.mark_reward_given(referrer_id, tier["count"])
            except Exception as e:
                log.error(f"Ошибка записи в Google Sheets (mark_reward_given): {e}")
            try:
                await bot.send_message(
                    referrer_id,
                    texts.REWARD_UNLOCKED.format(count=tier["count"], reward=tier["reward"]),
                )
            except Exception as e:
                log.warning(f"Не удалось уведомить о бонусе {referrer_id}: {e}")
            await log_to_admin_channel(
                f"🎁 Реферальный бонус разблокирован: id {referrer_id}, "
                f"{tier['count']} друзей → {tier['reward']}"
            )

    try:
        await bot.send_message(referrer_id, texts.REFERRAL_NEW_FRIEND.format(count=count))
    except Exception:
        pass


async def schedule_upsell(user_id: int, tariff: str):
    """Ставит апсейл-сообщение с задержкой (через APScheduler)."""
    delay_seconds = 60 * 60 * 3  # через 3 часа после регистрации, поправь под себя

    async def send_upsell():
        try:
            if tariff == config.TARIFF_FREE:
                await bot.send_message(
                    user_id,
                    texts.UPSELL_VIP_FOR_FREE.format(vip_link=config.VIP_UPGRADE_LINK),
                    reply_markup=upsell_kb(config.VIP_UPGRADE_LINK, "🚀 Взять VIP"),
                )
            else:
                await bot.send_message(
                    user_id,
                    texts.UPSELL_FLAGSHIP_FOR_VIP.format(flagship_link=config.FLAGSHIP_COURSE_LINK),
                    reply_markup=upsell_kb(config.FLAGSHIP_COURSE_LINK, "🎓 Узнать про курс"),
                )
        except Exception as e:
            log.warning(f"Не удалось отправить апсейл {user_id}: {e}")

    run_at = datetime.now() + timedelta(seconds=delay_seconds)
    scheduler.add_job(
        send_upsell,
        trigger="date",
        run_date=run_at,
        id=f"upsell_{user_id}_{tariff}",
        misfire_grace_time=3600,
        replace_existing=True,
    )


# ---------- хендлеры ----------

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    payload = command.args
    log.info(f"/start от {message.from_user.id} (@{message.from_user.username}), payload={payload!r}")
    tariff, ref_code = parse_start_payload(payload or "")

    user = message.from_user
    bot_info = await bot.get_me()

    if tariff is None:
        await message.answer(
            texts.WELCOME_UNKNOWN,
            reply_markup=unknown_tariff_kb(config.INTENSIVE_SITE_LINK, config.SUPPORT_CONTACT_LINK),
        )
        await log_to_admin_channel(
            f"❓ Открыл(а) бота без тарифа (странная ссылка): "
            f"{user.full_name} (@{user.username or 'без username'}, id {user.id})"
        )
        return

    # Логируем в канал-журнал сразу, до всех обращений к Sheets, так человек
    # точно попадёт в журнал, даже если дальше что-то сломается
    tariff_label = config.TARIFF_NAMES.get(tariff, tariff)
    await log_to_admin_channel(
        f"🆕 Дошёл до бота, тариф {tariff_label}: {user.full_name} "
        f"(@{user.username or 'без username'}, id {user.id})"
        + (f", по рефссылке {ref_code}" if ref_code else "")
    )

    referred_by_id = safe_get_referrer_id(ref_code) if ref_code else None
    # нельзя реферить самого себя
    if referred_by_id == user.id:
        referred_by_id = None
        ref_code = None

    my_ref_code = safe_upsert_user(
        telegram_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        tariff=tariff,
        referred_by=ref_code if referred_by_id else None,
    )

    channel_link = await get_channel_invite_link(tariff)

    text = texts.WELCOME_VIP if tariff == config.TARIFF_VIP else texts.WELCOME_FREE
    my_ref_link = f"https://t.me/{bot_info.username}?start={tariff}_{my_ref_code}"

    full_text = text.format(channel_link=channel_link) + texts.REFERRAL_INTRO.format(
        ref_link=my_ref_link, tiers=texts.referral_tiers_text()
    )

    await message.answer(full_text, reply_markup=channel_kb(channel_link))
    await message.answer("Твоя личная реферальная ссылка 👇", reply_markup=referral_share_kb(my_ref_link))

    # уведомляем и награждаем того, кто пригласил
    if referred_by_id:
        await check_and_reward_referrer(referred_by_id)

    # ставим отложенный апсейл
    await schedule_upsell(user.id, tariff)


@dp.message(Command("moi_ref"))
async def cmd_my_ref(message: Message):
    if not SHEETS_READY:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=free_{local_ref_code(message.from_user.id)}"
        await message.answer(
            f"Твоя реферальная ссылка:\n{ref_link}\n\n"
            f"⚠️ Счётчик друзей сейчас недоступен (не настроена Google Таблица), "
            f"но ссылка рабочая.\n\n{texts.referral_tiers_text()}",
            reply_markup=referral_share_kb(ref_link),
        )
        return
    bot_info = await bot.get_me()
    try:
        user = sheets.get_user(message.from_user.id)
        count = sheets.get_referrals_count(message.from_user.id) if user else 0
    except Exception as e:
        log.error(f"Ошибка чтения Google Sheets (cmd_my_ref): {e}")
        await message.answer("Не получилось прочитать данные из таблицы, попробуй чуть позже.")
        return
    if not user:
        await message.answer("Не нашёл тебя в базе, напиши /start с своей ссылкой регистрации.")
        return
    ref_link = f"https://t.me/{bot_info.username}?start={user['tariff']}_{user['ref_code']}"
    await message.answer(
        f"Твоя реферальная ссылка:\n{ref_link}\n\nПриглашено друзей: {count}\n\n{texts.referral_tiers_text()}",
        reply_markup=referral_share_kb(ref_link),
    )


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    text_to_send = command.args
    if not text_to_send:
        await message.answer("Использование: /broadcast текст рассылки")
        return
    if not SHEETS_READY:
        await message.answer(
            "⚠️ Google Таблица не подключена, не могу собрать список получателей. "
            "Проверь переменные GOOGLE_SHEET_ID и GOOGLE_SERVICE_ACCOUNT_JSON на Railway."
        )
        return

    try:
        ids = sheets.get_all_broadcast_ids()
    except Exception as e:
        log.error(f"Ошибка чтения Google Sheets (cmd_broadcast): {e}")
        await message.answer("Не получилось прочитать список получателей из таблицы.")
        return
    sent, failed = 0, 0
    status_msg = await message.answer(f"Начинаю рассылку на {len(ids)} чел...")

    for uid in ids:
        try:
            await bot.send_message(uid, text_to_send)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # антифлуд, ~20 сообщений/сек

    await status_msg.edit_text(f"Готово ✅ Доставлено: {sent}, не доставлено: {failed}")


@dp.message(F.text.lower().contains("забрать бонус"))
async def claim_bonus(message: Message):
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🎁 Запрос на бонус от @{message.from_user.username or message.from_user.id} "
                f"(id {message.from_user.id})",
            )
        except Exception:
            pass
    await log_to_admin_channel(
        f"🎁 Запрос на выдачу бонуса: {message.from_user.full_name} "
        f"(@{message.from_user.username or 'без username'}, id {message.from_user.id})"
    )
    await message.answer("Заявку получила, бонус вышлю вручную в ближайшее время 🙌")


# ---------- запуск ----------

@dp.message()
async def fallback(message: Message):
    """Ловит всё, что не подошло под другие хэндлеры, чтобы бот никогда не молчал."""
    log.info(f"Необработанное сообщение от {message.from_user.id}: {message.text!r}")
    await message.answer(
        "Не совсем понял(а) сообщение 🙂\n"
        "Если ты пришёл(ла) по ссылке с сайта, попробуй открыть её ещё раз, "
        "либо напиши /start."
    )


async def main():
    global SHEETS_READY
    try:
        sheets.init_sheets()
        SHEETS_READY = True
        log.info("Google Sheets подключены")
    except Exception as e:
        log.error(
            f"Не удалось подключить Google Sheets: [{type(e).__name__}] {e!r}\n"
            "Бот всё равно запустится и будет регистрировать людей и выдавать ссылки на каналы, "
            "просто без записи в таблицу и без счётчика рефералов. "
            "Проверь переменные GOOGLE_SHEET_ID и GOOGLE_SERVICE_ACCOUNT_JSON на Railway, "
            "а также что таблица расшарена на email сервисного аккаунта с правами Редактора."
        )
    scheduler.start()
    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
