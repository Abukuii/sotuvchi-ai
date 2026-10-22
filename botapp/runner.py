"""Telegram botlarni ishga tushirish (aiogram 3, long polling).

Bitta jarayon barcha faol do'konlarning botlarini boshqaradi. Har 15 soniyada
bazadagi sozlamalar tekshiriladi: yangi token qo'shilsa bot ishga tushadi,
token o'zgarsa yoki bot o'chirilsa to'xtatiladi/qayta ishga tushadi.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramUnauthorizedError
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from asgiref.sync import sync_to_async
from django.db import close_old_connections

from conversations.engine import handle_message

from . import menu, owner
from shops import botconfig
from shops.models import Shop

logger = logging.getLogger(__name__)

GREETING = {
    "uz": "👋 Assalomu alaykum!\nMen «{shop}» do'koni yordamchisiman.\n\n🛍 Katalogni tugmalar orqali ko'ring yoki mahsulot, narx va buyurtma haqida oddiy yozing.",
    "ru": "👋 Здравствуйте!\nЯ помощник магазина «{shop}».\n\n🛍 Смотрите каталог кнопками или просто напишите о товаре, цене или заказе.",
}
GENERIC_ERROR = "Kechirasiz, xatolik yuz berdi. Birozdan keyin qayta yozing. / Произошла ошибка, попробуйте позже."
MAX_TELEGRAM_CHARS = 4000
NON_TEXT = "Iltimos, savolingizni matn ko'rinishida yozing. / Пожалуйста, напишите текстом."
CUSTOMER_FAILED = "⚠️ Mijozga xabar yuborib bo'lmadi. / Не удалось уведомить клиента."
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
    return reply, shop.effective_owner_id


@_db_task
def _menu_text(shop_id, user_id, username, full_name, text):
    shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    return (menu.handle_menu_text(shop, user_id, username, full_name, text), shop.effective_owner_id) if shop else (None, None)


@_db_task
def _menu_command(shop_id, user_id, username, full_name, command):
    shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    return (menu.handle_command(shop, user_id, username, full_name, command), shop.effective_owner_id) if shop else (None, None)


@_db_task
def _menu_callback(shop_id, user_id, username, full_name, data):
    shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    return (menu.handle_callback(shop, user_id, username, full_name, data), shop.effective_owner_id) if shop else (None, None)


@_db_task
def _shop_language(shop_id, user_id):
    from conversations.models import Customer

    c = Customer.objects.filter(shop_id=shop_id, telegram_id=user_id).first()
    shop = Shop.objects.filter(pk=shop_id).first()
    lang = c.language if c else (shop.default_language if shop else "uz")
    return lang if lang in menu.T else "uz"


@_db_task
def _owner_rows(shop_id: int, order_id: int):
    from orders.models import Order

    shop = Shop.objects.filter(pk=shop_id).first()
    order = Order.objects.filter(pk=order_id, shop_id=shop_id).first()
    return owner.order_rows(shop, order.pk, order.status) if shop and order else []


@_db_task
def _owner_action(shop_id: int, user_id: int, data: str):
    shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    return owner.handle_action(shop, user_id, data) if shop else None


def inline_markup(rows):
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


def reply_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in menu.menu_labels(lang)],
        resize_keyboard=True,
        is_persistent=True,
    )


BOT_COMMANDS = [
    BotCommand(command="menu", description="Menyu / Меню"),
    BotCommand(command="catalog", description="Katalog / Каталог"),
    BotCommand(command="cart", description="Savat / Корзина"),
    BotCommand(command="orders", description="Buyurtmalarim / Мои заказы"),
    BotCommand(command="info", description="Ma'lumot / Информация"),
    BotCommand(command="settings", description="Sozlamalar / Настройки"),
]


async def _notify_owner(bot: Bot, shop_id: int, owner_id, notice, order_id: int | None = None) -> None:
    if not notice:
        return
    if not owner_id:
        logger.warning("Do'kon %s egasi Telegramga ulanmagan: bildirishnoma yuborilmadi", shop_id)
        return
    markup = None
    if order_id:
        rows = await _owner_rows(shop_id, order_id)
        markup = inline_markup(rows)
    try:
        await bot.send_message(owner_id, notice, reply_markup=markup)
    except TelegramAPIError as exc:
        logger.warning("Egasiga xabar yuborib bo'lmadi (shop=%s): %s", shop_id, exc)


async def _send_screen(bot: Bot, chat_id: int, screen, lang: str, edit_message: Message | None = None) -> None:
    text = screen.text[:MAX_TELEGRAM_CHARS]
    markup = inline_markup(screen.rows)
    if edit_message is not None and screen.replace:
        try:
            await edit_message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest as exc:
            if "not modified" not in str(exc):
                await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")  # eski xabar o'chirilgan bo'lishi mumkin
    else:
        await bot.send_message(
            chat_id, text, reply_markup=markup if markup else (reply_menu(lang) if screen.show_menu else None), parse_mode="HTML"
        )
    if screen.followup_menu:
        await bot.send_message(chat_id, screen.followup_menu, reply_markup=reply_menu(lang))


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
        lang = await _shop_language(shop_id, user.id)
        await message.answer(GREETING.get(lang, GREETING["uz"]).format(shop=shop.name), reply_markup=reply_menu(lang))

    @router.message(Command("menu", "catalog", "cart", "orders", "info", "settings", "help"))
    async def on_command(message: Message, command: CommandObject, bot: Bot):
        user = message.from_user
        if user is None:
            return
        try:
            async with _lock_for(shop_id, user.id):
                screen, owner_id = await _menu_command(shop_id, user.id, user.username or "", user.full_name or "", command.command)
                lang = await _shop_language(shop_id, user.id)
        except Exception:
            logger.exception("Buyruqni qayta ishlashda xato (shop=%s)", shop_id)
            await message.answer(GENERIC_ERROR)
            return
        if screen is not None:
            await _send_screen(bot, message.chat.id, screen, lang)
            await _notify_owner(bot, shop_id, owner_id, screen.owner_notice, screen.owner_order_id)

    @router.message(F.text.in_(menu.LABEL_TO_KEY.keys()))
    async def on_menu_button(message: Message, bot: Bot):
        user = message.from_user
        if user is None or message.text is None:
            return
        try:
            async with _lock_for(shop_id, user.id):
                screen, owner_id = await _menu_text(shop_id, user.id, user.username or "", user.full_name or "", message.text)
                lang = await _shop_language(shop_id, user.id)
        except Exception:
            logger.exception("Menyu tugmasida xato (shop=%s)", shop_id)
            await message.answer(GENERIC_ERROR)
            return
        if screen is not None:
            await _send_screen(bot, message.chat.id, screen, lang)
            await _notify_owner(bot, shop_id, owner_id, screen.owner_notice, screen.owner_order_id)

    @router.callback_query(F.data.startswith("m:"))
    async def on_callback(call: CallbackQuery, bot: Bot):
        user = call.from_user
        message = call.message
        if not isinstance(message, Message) or message.chat.type != "private":
            await call.answer()
            return
        try:
            async with _lock_for(shop_id, user.id):
                screen, owner_id = await _menu_callback(shop_id, user.id, user.username or "", user.full_name or "", call.data or "")
                lang = await _shop_language(shop_id, user.id)
        except Exception:
            logger.exception("Tugma bosilganda xato (shop=%s)", shop_id)
            await call.answer(GENERIC_ERROR[:150], show_alert=True)
            return
        if screen is None:
            await call.answer()
            return
        try:
            await call.answer(screen.toast[:190] if screen.toast else None)
        except TelegramAPIError:
            pass  # eski tugma: javob muddati o'tgan bo'lishi mumkin
        await _send_screen(bot, message.chat.id, screen, lang, edit_message=message)
        await _notify_owner(bot, shop_id, owner_id, screen.owner_notice, screen.owner_order_id)

    @router.callback_query(F.data.startswith("o:"))
    async def on_owner_action(call: CallbackQuery, bot: Bot):
        message = call.message
        if not isinstance(message, Message) or message.chat.type != "private":
            await call.answer()
            return
        try:
            result = await _owner_action(shop_id, call.from_user.id, call.data or "")
        except Exception:
            logger.exception("Egasi tugmasida xato (shop=%s)", shop_id)
            await call.answer(GENERIC_ERROR[:150], show_alert=True)
            return
        if result is None:
            await call.answer()
            return
        try:
            await call.answer(result.toast[:190] if result.toast else None)
        except TelegramAPIError:
            pass
        if result.refresh:
            base = owner.strip_status(message.text or "")
            try:
                await message.edit_text((base + result.text_suffix)[:MAX_TELEGRAM_CHARS], reply_markup=inline_markup(result.rows))
            except TelegramBadRequest as exc:
                if "not modified" not in str(exc):
                    logger.warning("Egasi xabarini yangilab bo'lmadi (shop=%s): %s", shop_id, exc)
        if result.customer_chat_id and result.customer_text:
            try:
                await bot.send_message(result.customer_chat_id, result.customer_text)
            except TelegramAPIError as exc:
                logger.warning("Mijozga holat xabari yuborilmadi (shop=%s): %s", shop_id, exc)
                try:
                    await bot.send_message(call.from_user.id, CUSTOMER_FAILED)
                except TelegramAPIError:
                    pass

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
        markup = None
        if reply.awaiting_confirmation:  # AI buyurtma xulosasini ko'rsatdi: "Ha" yozmasdan tugma bilan tasdiqlash
            tt = menu.T[reply.lang if reply.lang in menu.T else "uz"]
            markup = inline_markup([[(tt["confirm"], f"m:ok:{reply.draft_version}"), (tt["cancel"], "m:no")]])
        await message.answer(reply.text[:MAX_TELEGRAM_CHARS], reply_markup=markup)
        await _notify_owner(bot, shop_id, owner_id, reply.owner_notice, reply.order_id)

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
        try:
            await bot.set_my_commands(BOT_COMMANDS)
        except TelegramAPIError as exc:
            logger.warning("Bot buyruqlarini o'rnatib bo'lmadi (shop=%s): %s", shop_id, exc)
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
    tokens = {pk: token for pk, token in tokens.items() if token}  # shifri ochilmaganlar o'tkazib yuboriladi
    env_pk = botconfig.env_shop_id()  # .env dagi TELEGRAM_BOT_TOKEN (panelda tokeni yo'q do'konga)
    if env_pk and env_pk not in tokens:
        tokens[env_pk] = botconfig.env_token()
    return tokens


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
