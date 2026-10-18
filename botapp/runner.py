"""Telegram botlarni ishga tushirish (aiogram 3, long polling).

Bitta jarayon barcha faol do'konlarning botlarini boshqaradi. Har 15 soniyada
bazadagi sozlamalar tekshiriladi: yangi token qo'shilsa bot ishga tushadi,
token o'zgarsa yoki bot o'chirilsa to'xtatiladi/qayta ishga tushadi.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.db import close_old_connections

from conversations.engine import handle_message
from shops.models import Shop

logger = logging.getLogger(__name__)

GREETING = {
    "uz": "Assalomu alaykum! Men «{shop}» do'koni yordamchisiman. Mahsulot, narx yoki buyurtma haqida yozing.",
    "ru": "Здравствуйте! Я помощник магазина «{shop}». Пишите о товарах, ценах или заказе.",
}
GENERIC_ERROR = "Kechirasiz, xatolik yuz berdi. Birozdan keyin qayta yozing. / Произошла ошибка, попробуйте позже."
MAX_TELEGRAM_CHARS = 4000
NON_TEXT = "Iltimos, savolingizni matn ko'rinishida yozing. / Пожалуйста, напишите текстом."
OWNER_LINKED = "✅ Ulandi! Yangi buyurtmalar va muhim xabarlar endi shu yerga keladi."


def _db_task(func):
    """Django ORM chaqiruvini alohida oqimda, ulanishlarni tozalab bajaradi."""

    def wrapper(*args, **kwargs):
        close_old_connections()
        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()

    return sync_to_async(wrapper, thread_sensitive=False)


@_db_task
def _get_shop(shop_id: int):
    return Shop.objects.filter(pk=shop_id, is_active=True).first()


@_db_task
def _link_owner(shop_id: int, code: str, telegram_id: int) -> bool:
    return Shop.link_owner(shop_id, code, telegram_id)


@_db_task
def _process(shop_id: int, telegram_id: int, username: str, full_name: str, text: str):
    shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    if shop is None:
        return None, None
    reply = handle_message(shop, telegram_id, username, full_name, text)
    return reply, shop.owner_telegram_id


@_db_task
def _save_username(shop_id: int, username: str) -> None:
    Shop.objects.filter(pk=shop_id).update(bot_username=username[:64])


# Bitta mijozning xabarlari ketma-ket ishlanadi (ikki marta "Ha" bosilsa ham poyga bo'lmasin)
_user_locks: dict[tuple[int, int], asyncio.Lock] = {}
_MAX_LOCKS = 10000


def _lock_for(shop_id: int, user_id: int) -> asyncio.Lock:
    if len(_user_locks) > _MAX_LOCKS:
        for key in [k for k, v in _user_locks.items() if not v.locked()]:
            del _user_locks[key]
    return _user_locks.setdefault((shop_id, user_id), asyncio.Lock())


def build_dispatcher(shop_id: int) -> Dispatcher:
    router = Router()
    router.message.filter(F.chat.type == "private")  # guruh va kanallarda javob bermaydi

    @router.message(Command("start"))
    async def on_start(message: Message, command: CommandObject, bot: Bot):
        user = message.from_user
        if user is None:
            return
        if command.args and await _link_owner(shop_id, command.args.strip(), user.id):
            await message.answer(OWNER_LINKED)
            return
        shop = await _get_shop(shop_id)
        if shop is None:
            return
        await message.answer(GREETING.get(shop.default_language, GREETING["uz"]).format(shop=shop.name))

    @router.message(F.text)
    async def on_text(message: Message, bot: Bot):
        user = message.from_user
        if user is None or message.text is None:
            return
        try:
            await bot.send_chat_action(message.chat.id, "typing")
        except TelegramAPIError:
            pass
        try:
            async with _lock_for(shop_id, user.id):
                reply, owner_id = await _process(
                    shop_id, user.id, user.username or "", user.full_name or "", message.text
                )
        except Exception:
            logger.exception("Xabarni qayta ishlashda xato (shop=%s)", shop_id)
            await message.answer(GENERIC_ERROR)
            return
        if reply is None:
            return
        await message.answer(reply.text[:MAX_TELEGRAM_CHARS])
        if reply.owner_notice:
            if owner_id:
                try:
                    await bot.send_message(owner_id, reply.owner_notice)
                except TelegramAPIError as exc:
                    logger.warning("Egasiga xabar yuborib bo'lmadi (shop=%s): %s", shop_id, exc)
            else:
                logger.warning("Do'kon %s egasi Telegramga ulanmagan: bildirishnoma yuborilmadi", shop_id)

    @router.message()
    async def on_other(message: Message):
        await message.answer(NON_TEXT)

    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def _run_one(shop_id: int, token: str, bad_tokens: dict[int, str]) -> None:
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        await _save_username(shop_id, me.username or "")
        logger.info("Bot ishga tushdi: @%s (shop=%s)", me.username, shop_id)
        await build_dispatcher(shop_id).start_polling(bot, handle_signals=False, close_bot_session=False)
    except TelegramUnauthorizedError:
        bad_tokens[shop_id] = token  # token o'zgarmaguncha qayta urinmaymiz
        logger.error("Bot tokeni noto'g'ri (shop=%s). Panelda tokenni tekshiring.", shop_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Bot to'xtadi (shop=%s)", shop_id)
    finally:
        await bot.session.close()


@_db_task
def _active_shops() -> dict[int, str]:
    tokens = {s.pk: s.bot_token for s in Shop.objects.filter(is_active=True).exclude(token_encrypted="")}
    return {pk: token for pk, token in tokens.items() if token}  # shifri ochilmaganlar o'tkazib yuboriladi


async def supervise(refresh_seconds: int = 15) -> None:
    running: dict[int, tuple[str, asyncio.Task]] = {}
    bad_tokens: dict[int, str] = {}
    try:
        while True:
            wanted = await _active_shops()
            for shop_id, (token, task) in list(running.items()):
                if shop_id not in wanted or wanted[shop_id] != token or task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    del running[shop_id]
            for shop_id, token in wanted.items():
                if shop_id in running or bad_tokens.get(shop_id) == token:
                    continue
                running[shop_id] = (token, asyncio.create_task(_run_one(shop_id, token, bad_tokens)))
            await asyncio.sleep(refresh_seconds)
    finally:
        for _, task in running.values():
            task.cancel()
        await asyncio.gather(*(t for _, t in running.values()), return_exceptions=True)
