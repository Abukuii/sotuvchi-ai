"""Bot tugmalari, katalog, savat, sozlamalar: menyu mantig'i va aiogram darajasidagi oqim."""
import asyncio
from datetime import datetime

from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from django.contrib.auth.models import User as DjangoUser
from django.test import TestCase, TransactionTestCase

from catalog.models import Product
from conversations.models import Conversation, Customer
from orders.models import Order
from shops.models import Shop

from . import menu, runner
from .tests import CUSTOMER_ID, OWNER_ID, TOKEN, FakeSession, make_update


def make_shop(name="owner", **extra):
    user = DjangoUser.objects.create_user(name, password="x12345678!")
    return Shop.objects.create(owner=user, name=f"{name} do'koni", owner_telegram_id=OWNER_ID, **extra)


def seed(shop):
    return {
        "shirt": Product.objects.create(shop=shop, name="Ko'ylak", category="Kiyim", price=180000, stock=12, description="Paxta"),
        "bag": Product.objects.create(shop=shop, name="Sumka", category="Aksessuar", price=250000, stock=5),
        "shoe": Product.objects.create(shop=shop, name="Krossovka", category="Poyabzal", price=420000, stock=1),
        "gone": Product.objects.create(shop=shop, name="Tugagan narsa", category="Kiyim", price=1000, stock=0),
    }


def labels(screen):
    return [text for row in screen.rows for text, _ in row]


def callbacks(screen):
    return [data for row in screen.rows for _, data in row]


class MenuLogicTests(TestCase):
    def setUp(self):
        self.shop = make_shop()
        self.p = seed(self.shop)

    def ctx(self, tg=CUSTOMER_ID):
        return menu.get_ctx(self.shop, tg, "ali", "Ali V")

    def cb(self, data, tg=CUSTOMER_ID):
        return menu.handle_callback(self.shop, tg, "ali", "Ali V", data)

    # --- katalog

    def test_categories_lists_each_category_with_counts(self):
        screen = self.cb("m:cat:0")
        self.assertEqual(len(screen.rows) - 1, 3)  # 3 toifa + menyu tugmasi
        self.assertIn("Kiyim (2)", labels(screen))

    def test_single_category_skips_to_products(self):
        Product.objects.exclude(category="Kiyim").delete()
        screen = self.cb("m:cat:0")
        self.assertIn("Kiyim", screen.text)
        self.assertTrue(any(c.startswith("m:it:") for c in callbacks(screen)))

    def test_uncategorized_products_go_to_other(self):
        Product.objects.create(shop=self.shop, name="Nomsiz", price=5, stock=1)
        screen = self.cb("m:cat:0")
        self.assertIn("Boshqa (1)", labels(screen))

    def test_products_list_marks_sold_out_and_paginates(self):
        for i in range(10):
            Product.objects.create(shop=self.shop, name=f"Mahsulot {i:02d}", category="Ko'p", price=1000 + i, stock=1)
        cats = menu._categories(self.shop, "uz")
        idx = cats.index("Ko'p")
        page0 = self.cb(f"m:ls:{idx}:0")
        self.assertIn("(1/2)", page0.text)
        self.assertEqual(sum(1 for c in callbacks(page0) if c.startswith("m:it:")), menu.PAGE_SIZE)
        self.assertIn(f"m:ls:{idx}:1", callbacks(page0))
        page1 = self.cb(f"m:ls:{idx}:1")
        self.assertIn(f"m:ls:{idx}:0", callbacks(page1))
        clamped = self.cb(f"m:ls:{idx}:99")  # chegaradan tashqari sahifa xavfsiz
        self.assertIn("(2/2)", clamped.text)
        kiyim = self.cb(f"m:ls:{cats.index('Kiyim')}:0")
        self.assertTrue(any(label.startswith("✖") for label in labels(kiyim)))

    def test_product_card_shows_price_stock_and_qty_controls(self):
        cat = menu._categories(self.shop, "uz").index("Poyabzal")
        screen = self.cb(f"m:it:{self.p['shoe'].pk}:{cat}:0")
        self.assertIn("<b>420 000</b>", screen.text)
        self.assertIn("Oz qoldi: 1", screen.text)
        # qoldiq 1 bo'lgani uchun "+" miqdorni oshirmaydi
        self.assertIn(f"m:q:{self.p['shoe'].pk}:1:{cat}:0", callbacks(screen))

    def test_sold_out_card_has_no_add_button(self):
        screen = self.cb(f"m:it:{self.p['gone'].pk}:0:0")
        self.assertIn("Hozir omborda yo'q", screen.text)
        self.assertFalse(any(c.startswith("m:add:") for c in callbacks(screen)))

    def test_qty_selector_caps_at_stock(self):
        screen = self.cb(f"m:q:{self.p['bag'].pk}:500:0:0")
        self.assertTrue(any(l == "5" for l in labels(screen)))

    def test_unknown_or_foreign_product_is_safe(self):
        other_shop = make_shop("other")
        foreign = Product.objects.create(shop=other_shop, name="Begona", price=1, stock=5)
        for pid in (999999, foreign.pk):
            screen = self.cb(f"m:it:{pid}:0:0")
            self.assertIn("mavjud emas", screen.text)
            self.cb(f"m:add:{pid}:1:0:0")
        self.assertEqual(self.ctx().conv.draft, {})

    def test_html_in_names_is_escaped_everywhere(self):
        evil = Product.objects.create(shop=self.shop, name="<b>Zarar</b> & <a href='x'>", category="<i>X</i>", price=100, stock=3, description="<script>")
        self.cb(f"m:add:{evil.pk}:1:0:0")
        pages = [self.cb(f"m:it:{evil.pk}:0:0"), self.cb("m:cart"), self.cb("m:cat:0")]
        pages.append(self.cb(f"m:ls:{menu._categories(self.shop, 'uz').index('<i>X</i>')}:0"))
        for screen in pages:
            self.assertNotIn("<script>", screen.text)
            self.assertNotIn("<a href", screen.text)
            self.assertNotIn("<b>Zarar", screen.text)
        self.assertIn("&lt;b&gt;Zarar&lt;/b&gt; &amp;", pages[1].text)

    def test_shop_info_is_escaped(self):
        Shop.objects.filter(pk=self.shop.pk).update(work_hours="<b>9-18</b>", name="A&B <i>")
        self.shop.refresh_from_db()
        text = self.cb("m:info").text
        self.assertIn("&lt;b&gt;9-18&lt;/b&gt;", text)
        self.assertIn("A&amp;B &lt;i&gt;", text)

    def test_cart_has_distinct_product_limit(self):
        for i in range(menu.MAX_CART_LINES + 1):
            p = Product.objects.create(shop=self.shop, name=f"Tovar {i}", price=10, stock=5)
            screen = self.cb(f"m:add:{p.pk}:1:0:0")
        self.assertIn(str(menu.MAX_CART_LINES), screen.toast)
        self.assertEqual(len(self.ctx().conv.draft["items"]), menu.MAX_CART_LINES)
        # savat to'lgan bo'lsa ham mavjud mahsulot miqdorini oshirish mumkin
        first = Product.objects.get(name="Tovar 0")
        self.assertIn("qo'shildi", self.cb(f"m:add:{first.pk}:1:0:0").toast)

    # --- savat

    def test_add_to_cart_and_totals(self):
        self.cb(f"m:add:{self.p['shirt'].pk}:2:0:0")
        self.cb(f"m:add:{self.p['bag'].pk}:1:0:0")
        screen = self.cb("m:cart")
        self.assertIn("Ko'ylak × 2 — <b>360 000</b>", screen.text)
        self.assertIn("Jami: 610 000", screen.text)

    def test_adding_same_product_merges_and_caps_at_stock(self):
        pid = self.p["shoe"].pk
        self.cb(f"m:add:{pid}:1:0:0")
        screen = self.cb(f"m:add:{pid}:1:0:0")
        self.assertIn("faqat 1 dona", screen.toast)
        self.assertEqual(self.ctx().conv.draft["items"], [{"product_id": pid, "quantity": 1}])

    def test_cannot_add_sold_out(self):
        screen = self.cb(f"m:add:{self.p['gone'].pk}:1:0:0")
        self.assertIn("omborda yo'q", screen.toast)
        self.assertEqual(self.ctx().conv.draft, {})

    def test_cart_quantity_buttons_and_remove(self):
        pid = self.p["shirt"].pk
        self.cb(f"m:add:{pid}:2:0:0")
        self.cb(f"m:cq:{pid}:1")
        self.assertEqual(self.ctx().conv.draft["items"][0]["quantity"], 3)
        self.cb(f"m:cq:{pid}:-1")
        self.cb(f"m:cq:{pid}:-1")
        self.assertEqual(self.ctx().conv.draft["items"][0]["quantity"], 1)
        screen = self.cb(f"m:cq:{pid}:-1")  # 0 ga tushsa, savatdan chiqadi
        self.assertIn("bo'sh", screen.text)
        self.assertEqual(self.ctx().conv.draft, {})

    def test_cart_increase_is_capped_by_stock(self):
        pid = self.p["bag"].pk
        self.cb(f"m:add:{pid}:5:0:0")
        screen = self.cb(f"m:cq:{pid}:1")
        self.assertIn("faqat 5 dona", screen.toast)
        self.assertEqual(self.ctx().conv.draft["items"][0]["quantity"], 5)

    def test_remove_and_clear(self):
        self.cb(f"m:add:{self.p['shirt'].pk}:1:0:0")
        self.cb(f"m:add:{self.p['bag'].pk}:1:0:0")
        self.cb(f"m:cd:{self.p['shirt'].pk}")
        self.assertEqual([i["product_id"] for i in self.ctx().conv.draft["items"]], [self.p["bag"].pk])
        self.cb("m:cc")
        self.assertEqual(self.ctx().conv.draft, {})

    def test_deactivated_product_drops_out_of_cart(self):
        self.cb(f"m:add:{self.p['shirt'].pk}:1:0:0")
        Product.objects.filter(pk=self.p["shirt"].pk).update(is_active=False)
        self.assertIn("bo'sh", self.cb("m:cart").text)

    def test_carts_are_per_customer(self):
        self.cb(f"m:add:{self.p['shirt'].pk}:1:0:0", tg=1)
        self.assertIn("bo'sh", self.cb("m:cart", tg=2).text)

    # --- buyurtma berish

    def fill_cart(self):
        self.cb(f"m:add:{self.p['shirt'].pk}:2:0:0")

    def set_draft(self, **fields):
        ctx = self.ctx()
        draft = dict(ctx.conv.draft)
        draft.update(fields)
        Conversation.objects.filter(pk=ctx.conv.pk).update(draft=draft)

    def test_checkout_asks_missing_fields_in_order(self):
        self.fill_cart()
        self.assertIn("ismingizni", self.cb("m:co").text)
        self.set_draft(customer_name="Otabek")
        self.assertIn("telefon", self.cb("m:co").text)
        self.set_draft(phone="+998901112233")
        self.assertIn("manzil", self.cb("m:co").text.lower())

    def test_checkout_with_empty_cart(self):
        self.assertIn("bo'sh", self.cb("m:co").text)

    def complete_checkout(self):
        self.fill_cart()
        self.set_draft(customer_name="Otabek", phone="+998901112233", address="Jizzax, Navoiy 10")
        return self.cb("m:co")

    def test_full_button_flow_creates_order_and_reduces_stock(self):
        screen = self.complete_checkout()
        self.assertIn("Jami: 360 000", screen.text)
        confirm_cb = next(c for c in callbacks(screen) if c.startswith("m:ok:"))
        self.assertTrue(self.ctx().conv.awaiting_confirmation)
        done = self.cb(confirm_cb)
        order = Order.objects.get()
        self.assertIn(f"№{order.pk}", done.text)
        self.assertEqual(order.total, 360000)
        self.assertEqual(order.customer.telegram_id, CUSTOMER_ID)
        self.assertEqual(Product.objects.get(pk=self.p["shirt"].pk).stock, 10)
        self.assertIn("Yangi buyurtma", done.owner_notice)
        self.assertEqual(self.ctx().conv.draft, {})

    def test_double_confirm_creates_single_order(self):
        screen = self.complete_checkout()
        confirm_cb = next(c for c in callbacks(screen) if c.startswith("m:ok:"))
        self.cb(confirm_cb)
        again = self.cb(confirm_cb)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Product.objects.get(pk=self.p["shirt"].pk).stock, 10)
        self.assertIsNone(again.owner_notice)

    def test_stale_confirm_button_does_not_confirm_changed_order(self):
        screen = self.complete_checkout()
        old_cb = next(c for c in callbacks(screen) if c.startswith("m:ok:"))
        self.cb(f"m:add:{self.p['bag'].pk}:1:0:0")  # savat o'zgardi
        self.set_draft(customer_name="Otabek", phone="+998901112233", address="Jizzax")
        fresh = self.cb("m:co")
        stale = self.cb(old_cb)
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn("o'zgargan", stale.text)
        new_cb = next(c for c in callbacks(fresh) if c.startswith("m:ok:"))
        self.assertNotEqual(old_cb, new_cb)
        self.cb(new_cb)
        self.assertEqual(Order.objects.get().total, 610000)

    def test_forged_confirm_without_pending_order(self):
        self.fill_cart()
        screen = self.cb("m:ok:deadbeef")
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn("yo'q", screen.text)

    def test_stock_shortage_at_confirm(self):
        screen = self.complete_checkout()
        Product.objects.filter(pk=self.p["shirt"].pk).update(stock=1)
        result = self.cb(next(c for c in callbacks(screen) if c.startswith("m:ok:")))
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn("qoldig'i yetmay qoldi", result.text)
        self.assertEqual(Product.objects.get(pk=self.p["shirt"].pk).stock, 1)

    def test_cancel_clears_cart(self):
        self.complete_checkout()
        screen = self.cb("m:no")
        self.assertIn("bekor", screen.text.lower())
        self.assertEqual(self.ctx().conv.draft, {})
        self.assertFalse(self.ctx().conv.awaiting_confirmation)

    def test_prefill_from_previous_order(self):
        screen = self.complete_checkout()
        self.cb(next(c for c in callbacks(screen) if c.startswith("m:ok:")))
        self.fill_cart()
        again = self.cb("m:co")
        self.assertIn("Otabek", again.text)
        self.assertIn("+998901112233", again.text)
        self.assertTrue(any(c.startswith("m:ok:") for c in callbacks(again)))

    def test_prefill_not_taken_from_other_customer(self):
        screen = self.complete_checkout()
        self.cb(next(c for c in callbacks(screen) if c.startswith("m:ok:")))
        self.cb(f"m:add:{self.p['bag'].pk}:1:0:0", tg=2)
        self.assertIn("ismingizni", self.cb("m:co", tg=2).text)

    # --- boshqa bo'limlar

    def test_orders_screen(self):
        self.assertIn("Hali buyurtma", self.cb("m:ord").text)
        screen = self.complete_checkout()
        self.cb(next(c for c in callbacks(screen) if c.startswith("m:ok:")))
        text = self.cb("m:ord").text
        self.assertIn("360 000", text)
        self.assertIn("Yangi", text)
        self.assertNotIn("360 000", self.cb("m:ord", tg=2).text)

    def test_info_screen_and_operator(self):
        Shop.objects.filter(pk=self.shop.pk).update(work_hours="9:00-18:00", delivery_info="Jizzax bo'ylab bepul")
        self.shop.refresh_from_db()
        info = self.cb("m:info")
        self.assertIn("9:00-18:00", info.text)
        self.assertIn("bepul", info.text)
        op = self.cb("m:op")
        self.assertIn("javob kutmoqda", op.owner_notice)
        self.assertTrue(self.ctx().conv.needs_attention)

    def test_info_when_owner_did_not_fill(self):
        self.assertIn("hali kiritmagan", self.cb("m:info").text)

    def test_language_switch(self):
        screen = self.cb("m:lang:ru")
        self.assertEqual(Customer.objects.get(telegram_id=CUSTOMER_ID).language, "ru")
        self.assertIn("Настройки", screen.text)
        self.assertIn("Меню", " ".join(labels(self.cb("m:cat:0"))))
        self.assertEqual(menu.menu_labels("ru")[0][0], "🛍 Каталог")
        bad = self.cb("m:lang:xx")  # noma'lum til e'tiborsiz
        self.assertEqual(Customer.objects.get(telegram_id=CUSTOMER_ID).language, "ru")
        self.assertTrue(bad.rows)

    def test_delete_my_data_keeps_orders(self):
        screen = self.complete_checkout()
        self.cb(next(c for c in callbacks(screen) if c.startswith("m:ok:")))
        ask = self.cb("m:del")
        self.assertIn("m:delyes", callbacks(ask))
        self.assertTrue(Customer.objects.filter(telegram_id=CUSTOMER_ID).exists())  # so'rovning o'zi o'chirmaydi
        self.cb("m:delyes")
        self.assertFalse(Customer.objects.filter(telegram_id=CUSTOMER_ID).exists())
        self.assertEqual(Order.objects.count(), 1)

    def test_garbage_callbacks_return_home_without_error(self):
        for data in ["", "x", "m", "m:zzz", "m:it:abc:1:2", "m:ls", "m:q:1", "m:cq:1", "m:add:1", "m:" + "9" * 80, "m:cat:-5", "m:ls:999:0"]:
            screen = self.cb(data)
            self.assertTrue(screen.text, data)

    def test_menu_text_matching(self):
        self.assertIsNotNone(menu.handle_menu_text(self.shop, 1, "", "", "🛍 Katalog"))
        self.assertIsNotNone(menu.handle_menu_text(self.shop, 1, "", "", "🛒 Корзина"))
        self.assertIsNone(menu.handle_menu_text(self.shop, 1, "", "", "Katalog bormi?"))

    def test_empty_catalog(self):
        Product.objects.all().delete()
        self.assertIn("bo'sh", self.cb("m:cat:0").text)

    def test_callback_data_within_telegram_limit(self):
        for p in self.p.values():
            for screen in (self.cb(f"m:it:{p.pk}:0:0"), self.cb("m:cat:0"), self.cb("m:cart")):
                for data in callbacks(screen):
                    self.assertLessEqual(len(data.encode()), 64, data)


# ---------- aiogram darajasida ----------

def make_callback(data, user_id=CUSTOMER_ID, update_id=100):
    msg = Message(message_id=7, date=datetime.now(), chat=Chat(id=user_id, type="private"), text="old")
    call = CallbackQuery(
        id=str(update_id),
        from_user=User(id=user_id, is_bot=False, first_name="Ali", username="ali_v"),
        chat_instance="x",
        message=msg,
        data=data,
    )
    return Update(update_id=update_id, callback_query=call)


class BotButtonFlowTests(TransactionTestCase):
    def setUp(self):
        self.shop = make_shop()
        self.shop.bot_token = TOKEN
        self.shop.save()
        self.p = seed(self.shop)
        self.session = FakeSession()
        self.bot = Bot(token=TOKEN, session=self.session)
        self.dp = runner.build_dispatcher(self.shop.pk)

    def feed(self, *updates):
        async def run():
            for u in updates:
                await self.dp.feed_update(self.bot, u)

        asyncio.run(run())

    def methods(self, cls):
        return [m for m in self.session.calls if isinstance(m, cls)]

    def test_start_shows_reply_keyboard(self):
        self.feed(make_update("/start"))
        markup = self.methods(SendMessage)[0].reply_markup
        texts = [b.text for row in markup.keyboard for b in row]
        self.assertIn("🛍 Katalog", texts)
        self.assertIn("🛒 Savat", texts)

    def test_menu_button_opens_catalog_without_calling_ai(self):
        from unittest import mock

        with mock.patch("botapp.runner.handle_message", side_effect=AssertionError("AI chaqirilmasligi kerak")):
            self.feed(make_update("🛍 Katalog"))
        sent = self.methods(SendMessage)[-1]
        self.assertIn("Toifani tanlang", sent.text)
        data = [b.callback_data for row in sent.reply_markup.inline_keyboard for b in row]
        self.assertTrue(any(d.startswith("m:ls:") for d in data))

    def test_screens_are_sent_with_html_parse_mode_and_ai_replies_are_not(self):
        self.feed(make_update("/cart"))
        self.assertEqual(self.methods(SendMessage)[-1].parse_mode, "HTML")
        self.feed(make_update("Ko'ylak narxi qancha?", update_id=2))
        self.assertNotEqual(self.methods(SendMessage)[-1].parse_mode, "HTML")  # AI matni teg sifatida talqin qilinmasin

    def test_slash_commands(self):
        self.feed(make_update("/cart"), make_update("/settings", update_id=2), make_update("/orders", update_id=3))
        texts = [m.text for m in self.methods(SendMessage)]
        self.assertIn("Savatingiz bo'sh", texts[0])
        self.assertIn("Sozlamalar", texts[1])
        self.assertIn("Hali buyurtma", texts[2])

    def test_callback_edits_message_and_answers(self):
        self.feed(make_callback("m:cat:0"))
        self.assertEqual(len(self.methods(AnswerCallbackQuery)), 1)
        edit = self.methods(EditMessageText)[0]
        self.assertIn("Toifani tanlang", edit.text)

    def test_add_to_cart_toast(self):
        self.feed(make_callback(f"m:add:{self.p['shirt'].pk}:1:0:0"))
        self.assertIn("qo'shildi", self.methods(AnswerCallbackQuery)[0].text)

    def test_full_order_by_buttons_notifies_owner(self):
        self.feed(make_callback(f"m:add:{self.p['shirt'].pk}:1:0:0", update_id=1), make_callback("m:co", update_id=2))
        self.feed(make_update("Otabek", update_id=3), make_update("+998901112233", update_id=4), make_update("Jizzax, Navoiy 10", update_id=5))
        summary = self.methods(SendMessage)[-1]
        buttons = [b for row in summary.reply_markup.inline_keyboard for b in row]
        confirm = next(b for b in buttons if b.callback_data.startswith("m:ok:"))
        self.assertIn("Jami", summary.text)
        self.feed(make_callback(confirm.callback_data, update_id=6))
        self.assertEqual(Order.objects.count(), 1)
        owner = [m.text for m in self.session.sent(OWNER_ID)]
        self.assertIn("Yangi buyurtma", owner[-1])

    def test_callback_in_group_is_ignored(self):
        msg = Message(message_id=7, date=datetime.now(), chat=Chat(id=-100, type="supergroup"), text="x")
        call = CallbackQuery(id="1", from_user=User(id=5, is_bot=False, first_name="X"), chat_instance="x", message=msg, data="m:cat:0")
        self.feed(Update(update_id=1, callback_query=call))
        self.assertEqual(self.methods(EditMessageText), [])
        self.assertEqual(Customer.objects.count(), 0)

    def test_stale_message_edit_failure_falls_back_to_new_message(self):
        from aiogram.exceptions import TelegramBadRequest

        original = self.session.make_request

        async def failing(bot, method, timeout=None):
            if isinstance(method, EditMessageText):
                raise TelegramBadRequest(method=method, message="Bad Request: message to edit not found")
            return await original(bot, method, timeout)

        self.session.make_request = failing
        self.feed(make_callback("m:cat:0"))
        self.assertIn("Toifani tanlang", self.methods(SendMessage)[-1].text)

    def test_message_not_modified_is_silent(self):
        from aiogram.exceptions import TelegramBadRequest

        original = self.session.make_request

        async def not_modified(bot, method, timeout=None):
            if isinstance(method, EditMessageText):
                raise TelegramBadRequest(method=method, message="Bad Request: message is not modified")
            return await original(bot, method, timeout)

        self.session.make_request = not_modified
        self.feed(make_callback("m:cat:0"))
        self.assertEqual(self.methods(SendMessage), [])

    def test_ai_order_summary_gets_confirm_buttons(self):
        steps = ["Ko'ylak bormi?", "olaman", "Otabek", "+998901112233", "Jizzax, Navoiy 10"]
        self.feed(*[make_update(t, update_id=i + 1) for i, t in enumerate(steps)])
        summary = self.methods(SendMessage)[-1]
        self.assertIsNotNone(summary.reply_markup)
        data = [b.callback_data for row in summary.reply_markup.inline_keyboard for b in row]
        self.assertTrue(any(d.startswith("m:ok:") for d in data))
        self.feed(make_callback(next(d for d in data if d.startswith("m:ok:")), update_id=50))
        self.assertEqual(Order.objects.count(), 1)

    def test_error_in_callback_answers_alert(self):
        from unittest import mock

        with mock.patch("botapp.runner.menu.handle_callback", side_effect=RuntimeError("db")):
            self.feed(make_callback("m:cat:0"))
        answer = self.methods(AnswerCallbackQuery)[0]
        self.assertTrue(answer.show_alert)
