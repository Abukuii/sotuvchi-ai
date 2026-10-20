"""Telegram handlerlarini soxta Bot sessiyasi bilan sinash (haqiqiy Telegram kerak emas).

aiogram Dispatcher ga haqiqiy Update obyektlari beriladi, Telegramga ketadigan so'rovlar
FakeSession da yig'iladi. Shu bilan /start, javoblar, egasiga xabar, guruhlarni e'tiborsiz
qoldirish va xatolarni qayta ishlash tekshiriladi.
"""
import asyncio
from datetime import datetime
from unittest import mock

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendChatAction, SendMessage
from aiogram.types import Chat, Message, PhotoSize, Update, User
from django.contrib.auth.models import User as DjangoUser
from django.test import TransactionTestCase

from catalog.importer import build_template_xlsx, import_catalog
from catalog.models import Product
from conversations.models import Conversation
from orders.models import Order
from shops.models import Shop

from . import runner

TOKEN = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
OWNER_ID = 5550001
CUSTOMER_ID = 7770001


class FakeSession(BaseSession):
    """Telegramga ketadigan so'rovlarni yozib boradi."""

    def __init__(self):
        super().__init__()
        self.calls: list = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=len(self.calls),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Bot", username="demo_bot")
        return True

    def sent(self, chat_id=None):
        return [m for m in self.calls if isinstance(m, SendMessage) and (chat_id is None or m.chat_id == chat_id)]


def make_update(text=None, user_id=CUSTOMER_ID, chat_type="private", photo=False, update_id=1):
    message = Message(
        message_id=update_id,
        date=datetime.now(),
        chat=Chat(id=user_id if chat_type == "private" else -100500, type=chat_type),
        from_user=User(id=user_id, is_bot=False, first_name="Ali", last_name="Valiyev", username="ali_v"),
        text=text,
        photo=[PhotoSize(file_id="a", file_unique_id="b", width=1, height=1)] if photo else None,
    )
    return Update(update_id=update_id, message=message)


class BotHandlerTests(TransactionTestCase):
    def setUp(self):
        user = DjangoUser.objects.create_user("owner", password="x12345678!")
        self.shop = Shop.objects.create(owner=user, name="Test do'kon", owner_telegram_id=OWNER_ID)
        self.shop.bot_token = TOKEN
        self.shop.save()
        import_catalog(self.shop, "k.xlsx", build_template_xlsx())
        self.session = FakeSession()
        self.bot = Bot(token=TOKEN, session=self.session)
        self.dp = runner.build_dispatcher(self.shop.pk)

    def feed(self, *updates):
        async def run():
            for update in updates:
                await self.dp.feed_update(self.bot, update)

        asyncio.run(run())

    def texts(self, chat_id):
        return [m.text for m in self.session.sent(chat_id)]

    # --- /start

    def test_start_greets_customer(self):
        self.feed(make_update("/start"))
        self.assertIn("Test do'kon", self.texts(CUSTOMER_ID)[0])

    def test_owner_link_via_start_payload(self):
        code = self.shop.owner_link_code
        self.shop.owner_telegram_id = None
        self.shop.save()
        self.feed(make_update(f"/start {code}", user_id=OWNER_ID))
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.owner_telegram_id, OWNER_ID)
        self.assertIn("Ulandi", self.texts(OWNER_ID)[0])
        self.assertNotEqual(self.shop.owner_link_code, code)  # kod bir martalik

    def test_wrong_or_reused_link_code_does_not_hijack_notifications(self):
        code = self.shop.owner_link_code
        self.feed(make_update(f"/start {code}", user_id=111))  # birinchi ishlatish
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.owner_telegram_id, 111)
        self.feed(make_update(f"/start {code}", user_id=222, update_id=2))  # xuddi shu kod qayta
        self.feed(make_update("/start xato-kod", user_id=333, update_id=3))
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.owner_telegram_id, 111)

    # --- suhbat

    def test_customer_gets_answer_from_catalog(self):
        self.feed(make_update("Ko'ylak narxi qancha?"))
        reply = self.texts(CUSTOMER_ID)[0]
        self.assertIn("180000", reply)
        self.assertTrue(any(isinstance(c, SendChatAction) for c in self.session.calls))  # "yozmoqda..."

    def test_unknown_question_notifies_owner(self):
        self.feed(make_update("Dron bormi?"))
        owner_msgs = self.texts(OWNER_ID)
        self.assertEqual(len(owner_msgs), 1)
        self.assertIn("javob kutmoqda", owner_msgs[0])

    def test_full_order_over_telegram_notifies_owner(self):
        steps = ["Ko'ylak bormi?", "olaman", "Otabek", "+998901112233", "Jizzax, Navoiy 10", "ha"]
        self.feed(*[make_update(t, update_id=i + 1) for i, t in enumerate(steps)])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().customer_name, "Otabek")
        self.assertIn("Yangi buyurtma", self.texts(OWNER_ID)[-1])
        self.assertIn("qabul qilindi", self.texts(CUSTOMER_ID)[-1])

    def test_no_owner_linked_still_answers_customer(self):
        self.shop.owner_telegram_id = None
        self.shop.save()
        self.feed(make_update("Dron bormi?"))
        self.assertTrue(self.texts(CUSTOMER_ID))
        self.assertEqual(self.texts(OWNER_ID), [])

    def test_double_confirmation_creates_one_order(self):
        """Ikkita "Ha" bir vaqtda kelsa ham, bitta buyurtma va qoldiq bir marta kamayadi.

        Eslatma: bu butun yo'l uchun tutun-sinov. Poyga himoyasining o'zi (suhbat qatori qulfi)
        conversations.tests.ConfirmationFlowTests.test_create_order_is_idempotent_against_stale_state
        da aniq holat bilan tekshiriladi.
        """
        steps = ["Ko'ylak bormi?", "olaman", "Otabek", "+998901112233", "Jizzax, Navoiy 10"]
        self.feed(*[make_update(t, update_id=i + 1) for i, t in enumerate(steps)])

        async def both():
            await asyncio.gather(
                self.dp.feed_update(self.bot, make_update("ha", update_id=10)),
                self.dp.feed_update(self.bot, make_update("ha", update_id=11)),
            )

        asyncio.run(both())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Product.objects.get(sku="KY-001").stock, 11)

    # --- chegaralar va xatolar

    def test_group_chat_is_ignored(self):
        self.feed(make_update("Ko'ylak narxi?", chat_type="supergroup"))
        self.assertEqual(self.session.sent(), [])

    def test_non_text_gets_polite_hint(self):
        self.feed(make_update(None, photo=True))
        self.assertIn("matn", self.texts(CUSTOMER_ID)[0])

    def test_inactive_shop_does_not_answer(self):
        self.shop.is_active = False
        self.shop.save()
        self.feed(make_update("Salom"))
        self.assertEqual(self.session.sent(), [])

    def test_processing_error_gives_generic_reply_not_silence(self):
        with mock.patch("botapp.runner.handle_message", side_effect=RuntimeError("db down")):
            self.feed(make_update("Salom"))
        self.assertIn("xatolik", self.texts(CUSTOMER_ID)[0])

    def test_long_reply_is_truncated_for_telegram(self):
        from conversations.engine import BotReply

        with mock.patch("botapp.runner.handle_message", return_value=BotReply(text="x" * 9000)):
            self.feed(make_update("Salom"))
        self.assertLessEqual(len(self.texts(CUSTOMER_ID)[0]), 4000)

    def test_customer_messages_are_stored_per_customer(self):
        self.feed(make_update("Salom", user_id=1), make_update("Salom", user_id=2, update_id=2))
        self.assertEqual(Conversation.objects.count(), 2)


class SupervisorTests(TransactionTestCase):
    def test_active_shops_decrypts_tokens_and_skips_bad(self):
        user_a = DjangoUser.objects.create_user("a", password="x12345678!")
        user_b = DjangoUser.objects.create_user("b", password="x12345678!")
        a = Shop.objects.create(owner=user_a, name="A")
        a.bot_token = TOKEN
        a.save()
        b = Shop.objects.create(owner=user_b, name="B", is_active=False)
        b.bot_token = "987654321:AAH-zyxwvutsrqponmlkjihgfedcba98765"
        b.save()
        tokens = asyncio.run(runner._active_shops())
        self.assertEqual(tokens, {a.pk: TOKEN})
