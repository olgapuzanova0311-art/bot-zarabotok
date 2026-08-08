"""
Бот интенсива "AI-старт".

Что делает:
1. Принимает и бесплатных, и VIP-участников после оплаты (переход по диплинку вида
   https://t.me/<bot_username>?start=free   или   ?start=vip
   Ссылки с этими параметрами нужно поставить на кнопки "спасибо за оплату" / после формы GetCourse.
2. Сразу выдаёт ссылку на канал мероприятия.
3. Пишет каждого пользователя в Google Sheets (база для будущих рассылок).
4. Выдаёт каждому персональную реферальную ссылку и начисляет бонусы за приведённых друзей.
5. Через время присылает апсейл: бесплатным — апгрейд на VIP, VIP — на флагманский курс.
6. /broadcast <текст> — рассылка по всей базе (только для админов).

Деплой: см. README.md
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import sheets
import texts
from keyboards import channel_kb, upsell_kb, referral_share_kb

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()


# ---------- вспомогательные функции ----------

async def get_channel_invite_link(tariff: str) -> str:
    """
    Возвращает ссылку на нужный канал в зависимости от тарифа:
    - free -> канал мероприятия (EVENT_CHANNEL_*)
    - vip  -> отдельный VIP-канал (VIP_CHANNEL_*)
    Если указан числовой ID канала — пробуем создать одноразовую ссылку через API.
    Если не получилось (или ID не указан) — используем постоянную ссылку-приглашение.
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
    count = sheets.get_referrals_count(referrer_id)
    given = sheets.get_reward_tiers_given(referrer_id)

    for tier in config.REFERRAL_TIERS:
        if count >= tier["count"] and str(tier["count"]) not in given:
            sheets.mark_reward_given(referrer_id, tier["count"])
            try:
                await bot.send_message(
                    referrer_id,
                    texts.REWARD_UNLOCKED.format(count=tier["count"], reward=tier["reward"]),
                )
            except Exception as e:
                log.warning(f"Не удалось уведомить о бонусе {referrer_id}: {e}")

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

    scheduler.add_job(send_upsell, "date", run_date=None, id=f"upsell_{user_id}_{tariff}",
                       misfire_grace_time=3600, replace_existing=True,
                       next_run_time=__import__("datetime").datetime.now() + __import__("datetime").timedelta(seconds=delay_seconds))


# ---------- хендлеры ----------

@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    payload = command.args
    tariff, ref_code = parse_start_payload(payload or "")

    user = message.from_user
    bot_info = await bot.get_me()

    if tariff is None:
        await message.answer(texts.WELCOME_UNKNOWN)
        return

    referred_by_id = sheets.get_referrer_telegram_id(ref_code) if ref_code else None
    # нельзя реферить самого себя
    if referred_by_id == user.id:
        referred_by_id = None
        ref_code = None

    my_ref_code = sheets.upsert_user(
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
    bot_info = await bot.get_me()
    user = sheets.get_user(message.from_user.id)
    if not user:
        await message.answer("Не нашёл тебя в базе — напиши /start с своей ссылкой регистрации.")
        return
    ref_link = f"https://t.me/{bot_info.username}?start={user['tariff']}_{user['ref_code']}"
    count = sheets.get_referrals_count(message.from_user.id)
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

    ids = sheets.get_all_broadcast_ids()
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
    await message.answer("Заявку получила, бонус вышлю вручную в ближайшее время 🙌")


# ---------- запуск ----------

async def main():
    sheets.init_sheets()
    scheduler.start()
    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
