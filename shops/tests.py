from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from catalog.importer import build_template_xlsx
from catalog.models import Product
from conversations.models import Conversation, Customer
from orders.models import Order

from unittest import mock

from . import crypto, notify
from .models import AuditEvent, Shop

PASSWORD = "S3cure-pass-123"
TOKEN = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"


class BaseTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # throttle hisoblari testlar orasida aralashmasin


def make_user(name):
    user = User.objects.create_user(name, password=PASSWORD)
    shop = Shop.objects.create(owner=user, name=f"{name} do'koni")
    return user, shop


class AuthTests(BaseTestCase):
    def test_pages_require_login(self):
        for name in ["dashboard", "catalog", "orders", "conversations", "shop_settings"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/login/", response["Location"])

    def test_signup_creates_shop_and_logs_in(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "yangi", "password1": PASSWORD, "password2": PASSWORD, "shop_name": "Mening do'konim"},
        )
        self.assertRedirects(response, reverse("shop_settings"))
        self.assertEqual(Shop.objects.get(owner__username="yangi").name, "Mening do'konim")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_weak_password_rejected(self):
        response = self.client.post(
            reverse("signup"), {"username": "x", "password1": "12345678", "password2": "12345678", "shop_name": "A"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_logout_requires_post(self):
        user, _ = make_user("a")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)


class SettingsTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.shop = make_user("a")
        self.client.force_login(self.user)

    def payload(self, **extra):
        data = {"name": "Yangi nom", "bot_token": TOKEN, "default_language": "uz", "delivery_info": "", "work_hours": "", "extra_instructions": "", "is_active": "on"}
        data.update(extra)
        return data

    def test_token_saved_and_never_rendered(self):
        self.client.post(reverse("shop_settings"), self.payload())
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.bot_token, TOKEN)
        for name in ["shop_settings", "dashboard"]:
            self.assertNotIn(TOKEN, self.client.get(reverse(name)).content.decode())

    def test_blank_token_keeps_existing(self):
        self.client.post(reverse("shop_settings"), self.payload())
        self.client.post(reverse("shop_settings"), self.payload(bot_token="", name="Boshqa"))
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.bot_token, TOKEN)
        self.assertEqual(self.shop.name, "Boshqa")

    def test_invalid_token_rejected(self):
        response = self.client.post(reverse("shop_settings"), self.payload(bot_token="abc"))
        self.assertEqual(response.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.bot_token, "")

    def test_token_unique_across_shops(self):
        _, other = make_user("b")
        other.bot_token = TOKEN
        other.save()
        response = self.client.post(reverse("shop_settings"), self.payload())
        self.assertEqual(response.status_code, 200)

    def test_regenerate_link_resets_owner(self):
        self.shop.owner_telegram_id = 5
        self.shop.save()
        old = self.shop.owner_link_code
        self.client.post(reverse("regenerate_link"))
        self.shop.refresh_from_db()
        self.assertNotEqual(self.shop.owner_link_code, old)
        self.assertIsNone(self.shop.owner_telegram_id)


class CatalogViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.shop = make_user("a")
        self.client.force_login(self.user)

    def upload(self, name, content):
        return self.client.post(reverse("catalog_upload"), {"file": SimpleUploadedFile(name, content)}, follow=True)

    def test_upload_and_list(self):
        response = self.upload("k.xlsx", build_template_xlsx())
        self.assertContains(response, "3 ta yangi")
        self.assertContains(self.client.get(reverse("catalog")), escape("Erkaklar ko'ylagi"))

    def test_upload_garbage_shows_error(self):
        response = self.upload("k.xlsx", b"garbage")
        self.assertContains(response, escape("o'qib bo'lmadi"))
        self.assertEqual(Product.objects.count(), 0)

    def test_template_download(self):
        response = self.client.get(reverse("catalog_template"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])

    def test_product_crud(self):
        self.client.post(reverse("product_new"), {"name": "Qalam", "price": "5000", "stock": "10", "is_active": "on"})
        product = Product.objects.get()
        self.assertEqual(product.shop, self.shop)
        self.client.post(reverse("product_edit", args=[product.pk]), {"name": "Qalam 2", "price": "6000", "stock": "9"})
        product.refresh_from_db()
        self.assertEqual((product.name, int(product.price), product.is_active), ("Qalam 2", 6000, False))
        self.client.post(reverse("product_delete", args=[product.pk]))
        self.assertEqual(Product.objects.count(), 0)


class TenantIsolationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.a, self.shop_a = make_user("a")
        self.b, self.shop_b = make_user("b")
        self.product = Product.objects.create(shop=self.shop_a, name="Maxfiy", price=1000, stock=1)
        customer = Customer.objects.create(shop=self.shop_a, telegram_id=1)
        self.conv = Conversation.objects.create(customer=customer)
        self.order = Order.objects.create(shop=self.shop_a, customer_name="X", phone="+998900000000", address="Y")
        self.client.force_login(self.b)

    def test_other_users_objects_are_404(self):
        urls = [
            ("product_edit", self.product.pk, "get"),
            ("product_delete", self.product.pk, "post"),
            ("order_detail", self.order.pk, "get"),
            ("order_status", self.order.pk, "post"),
            ("conversation_detail", self.conv.pk, "get"),
        ]
        for name, pk, method in urls:
            response = getattr(self.client, method)(reverse(name, args=[pk]), {"status": "cancelled"})
            self.assertEqual(response.status_code, 404, name)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_NEW)

    def test_lists_do_not_leak(self):
        self.assertNotContains(self.client.get(reverse("catalog")), "Maxfiy")
        self.assertNotContains(self.client.get(reverse("orders")), "+998900000000")


class OrderViewTests(BaseTestCase):
    def test_status_change(self):
        user, shop = make_user("a")
        self.client.force_login(user)
        order = Order.objects.create(shop=shop, customer_name="X", phone="+998900000000", address="Y")
        self.client.post(reverse("order_status", args=[order.pk]), {"status": "delivered"})
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")
        self.client.post(reverse("order_status", args=[order.pk]), {"status": "hacked"})
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")



class TokenSecurityTests(BaseTestCase):
    def test_token_encrypted_at_rest(self):
        _, shop = make_user("a")
        shop.bot_token = TOKEN
        shop.save()
        raw = Shop.objects.values_list("token_encrypted", "token_hash").get(pk=shop.pk)
        self.assertNotIn("AAH-", raw[0])
        self.assertNotIn(TOKEN.split(":")[0], raw[0] + raw[1])
        self.assertEqual(Shop.objects.get(pk=shop.pk).bot_token, TOKEN)

    def test_db_enforces_unique_token(self):
        _, a = make_user("a")
        _, b = make_user("b")
        a.bot_token = TOKEN
        a.save()
        b.bot_token = TOKEN
        with self.assertRaises(IntegrityError), transaction.atomic():
            b.save()

    def test_wrong_key_returns_empty_not_crash(self):
        _, shop = make_user("a")
        shop.bot_token = TOKEN
        shop.save()
        with self.settings(TOKEN_ENCRYPTION_KEY="boshqa-kalit-" * 4):
            self.assertEqual(Shop.objects.get(pk=shop.pk).bot_token, "")
        self.assertEqual(crypto.decrypt("garbage"), "")

    def test_token_change_resets_owner_link(self):
        user, shop = make_user("a")
        shop.owner_telegram_id = 99
        shop.save()
        old_code = shop.owner_link_code
        self.client.force_login(user)
        self.client.post(reverse("shop_settings"), {"name": "X", "bot_token": TOKEN, "default_language": "uz", "is_active": "on"})
        shop.refresh_from_db()
        self.assertIsNone(shop.owner_telegram_id)
        self.assertNotEqual(shop.owner_link_code, old_code)

    def test_remove_token(self):
        user, shop = make_user("a")
        shop.bot_token = TOKEN
        shop.save()
        self.client.force_login(user)
        self.client.post(reverse("shop_settings"), {"name": "X", "remove_token": "on", "default_language": "uz", "is_active": "on"})
        shop.refresh_from_db()
        self.assertFalse(shop.has_token)

    def test_new_token_and_remove_together_rejected(self):
        user, shop = make_user("a")
        self.client.force_login(user)
        response = self.client.post(
            reverse("shop_settings"),
            {"name": "X", "bot_token": TOKEN, "remove_token": "on", "default_language": "uz", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        shop.refresh_from_db()
        self.assertFalse(shop.has_token)


class OwnerLinkTests(BaseTestCase):
    def test_link_code_is_single_use(self):
        _, shop = make_user("a")
        code = shop.owner_link_code
        self.assertTrue(Shop.link_owner(shop.pk, code, 111))
        shop.refresh_from_db()
        self.assertEqual(shop.owner_telegram_id, 111)
        self.assertNotEqual(shop.owner_link_code, code)
        # Havola boshqa odamga tushsa ham egasini almashtira olmaydi
        self.assertFalse(Shop.link_owner(shop.pk, code, 222))
        shop.refresh_from_db()
        self.assertEqual(shop.owner_telegram_id, 111)

    def test_wrong_or_empty_code(self):
        _, shop = make_user("a")
        self.assertFalse(Shop.link_owner(shop.pk, "xato", 1))
        self.assertFalse(Shop.link_owner(shop.pk, "", 1))

    def test_code_of_other_shop_does_not_work(self):
        _, a = make_user("a")
        _, b = make_user("b")
        self.assertFalse(Shop.link_owner(b.pk, a.owner_link_code, 5))


class ThrottleTests(BaseTestCase):
    def login(self, username, password):
        return self.client.post(reverse("login"), {"username": username, "password": password})

    def test_login_locks_after_failures_even_with_correct_password(self):
        make_user("a")
        for _ in range(5):
            self.assertEqual(self.login("a", "xato-parol").status_code, 200)
        self.assertEqual(self.login("a", PASSWORD).status_code, 429)

    def test_other_username_not_locked_by_one_victim(self):
        make_user("a")
        make_user("b")
        for _ in range(5):
            self.login("a", "xato")
        self.assertEqual(self.login("b", PASSWORD).status_code, 302)

    def test_successful_login_resets_counter(self):
        make_user("a")
        for _ in range(4):
            self.login("a", "xato")
        self.assertEqual(self.login("a", PASSWORD).status_code, 302)
        self.client.post(reverse("logout"))
        for _ in range(4):
            self.assertEqual(self.login("a", "xato").status_code, 200)

    def test_ip_wide_limit(self):
        with self.settings(LOGIN_IP_MAX_ATTEMPTS=3, LOGIN_MAX_ATTEMPTS=100):
            for i in range(3):
                self.login(f"user{i}", "xato")
            self.assertEqual(self.login("user9", "xato").status_code, 429)

    def test_signup_limit(self):
        with self.settings(SIGNUP_MAX_PER_HOUR=2):
            for i in range(2):
                self.client.post(reverse("signup"), {"username": f"yangi{i}", "password1": PASSWORD, "password2": PASSWORD, "shop_name": "D"})
                self.client.post(reverse("logout"))
            response = self.client.post(reverse("signup"), {"username": "yangi9", "password1": PASSWORD, "password2": PASSWORD, "shop_name": "D"})
        self.assertEqual(response.status_code, 429)
        self.assertFalse(User.objects.filter(username="yangi9").exists())

    def test_forwarded_header_ignored_unless_trusted(self):
        make_user("a")
        for i in range(5):
            self.client.post(reverse("login"), {"username": "a", "password": "xato"}, HTTP_X_FORWARDED_FOR=f"10.0.0.{i}")
        self.assertEqual(self.client.post(reverse("login"), {"username": "a", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="10.9.9.9").status_code, 429)


class ConversationDeleteTests(BaseTestCase):
    def test_delete_keeps_orders_removes_customer_data(self):
        user, shop = make_user("a")
        customer = Customer.objects.create(shop=shop, telegram_id=7, full_name="Ali")
        conv = Conversation.objects.create(customer=customer)
        conv.messages.create(role="user", text="salom")
        order = Order.objects.create(shop=shop, customer=customer, customer_name="Ali", phone="+998900000000", address="Y")
        self.client.force_login(user)
        self.client.post(reverse("conversation_delete", args=[conv.pk]))
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())
        self.assertEqual(conv.messages.model.objects.count(), 0)
        order.refresh_from_db()
        self.assertIsNone(order.customer)

    def test_cannot_delete_foreign_conversation_or_via_get(self):
        a, shop_a = make_user("a")
        b, _ = make_user("b")
        conv = Conversation.objects.create(customer=Customer.objects.create(shop=shop_a, telegram_id=1))
        self.client.force_login(b)
        self.assertEqual(self.client.post(reverse("conversation_delete", args=[conv.pk])).status_code, 404)
        self.client.force_login(a)
        self.assertEqual(self.client.get(reverse("conversation_delete", args=[conv.pk])).status_code, 405)
        self.assertTrue(Conversation.objects.filter(pk=conv.pk).exists())


class AdminAndHeadersTests(BaseTestCase):
    def test_admin_requires_staff_and_hides_tokens(self):
        user, shop = make_user("a")
        shop.bot_token = TOKEN
        shop.save()
        self.client.force_login(user)
        self.assertEqual(self.client.get("/admin/shops/shop/").status_code, 302)  # staff emas
        admin = User.objects.create_superuser("root", password=PASSWORD)
        self.client.force_login(admin)
        for path in ["/admin/shops/shop/", f"/admin/shops/shop/{shop.pk}/change/", "/admin/catalog/product/", "/admin/orders/order/", "/admin/conversations/conversation/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertNotIn(TOKEN, response.content.decode(), path)
            self.assertNotIn("token_encrypted", response.content.decode(), path)

    def test_security_headers(self):
        user, _ = make_user("a")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_product_limits(self):
        user, _ = make_user("a")
        self.client.force_login(user)
        response = self.client.post(reverse("product_new"), {"name": "A", "price": str(10**12), "stock": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        response = self.client.post(reverse("product_new"), {"name": "A", "price": "100", "stock": str(10**9)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)


class CustomerNotificationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.shop = make_user("a")
        self.shop.bot_token = TOKEN
        self.shop.save()
        self.customer = Customer.objects.create(shop=self.shop, telegram_id=424242, language="uz")
        self.order = Order.objects.create(
            shop=self.shop, customer=self.customer, customer_name="Ali", phone="+998900000000", address="Y"
        )
        self.client.force_login(self.user)

    def change(self, status, **extra):
        data = {"status": status, "notify": "on"}
        data.update(extra)
        return self.client.post(reverse("order_status", args=[self.order.pk]), data, follow=True)

    def test_status_change_notifies_customer(self):
        from unittest import mock

        import httpx

        ok = httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", "https://x/"))
        with mock.patch("shops.notify.httpx.post", return_value=ok) as post:
            response = self.change("delivered")
        args, kwargs = post.call_args
        self.assertIn(TOKEN, args[0])
        self.assertEqual(kwargs["json"]["chat_id"], 424242)
        self.assertIn(f"№{self.order.pk}", kwargs["json"]["text"])
        self.assertIn("yetkazildi", kwargs["json"]["text"])
        self.assertContains(response, "Mijozga Telegramda xabar yuborildi")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")

    def test_russian_customer_gets_russian_text(self):
        from unittest import mock

        import httpx

        self.customer.language = "ru"
        self.customer.save()
        ok = httpx.Response(200, json={}, request=httpx.Request("POST", "https://x/"))
        with mock.patch("shops.notify.httpx.post", return_value=ok) as post:
            self.change("cancelled")
        self.assertIn("отменён", post.call_args.kwargs["json"]["text"])

    def test_checkbox_off_same_status_and_new_do_not_send(self):
        from unittest import mock

        with mock.patch("shops.notify.httpx.post") as post:
            self.client.post(reverse("order_status", args=[self.order.pk]), {"status": "confirmed"})  # notify yo'q
            self.change("confirmed")  # holat o'zgarmadi
            self.change("new")  # "yangi" uchun matn yo'q
        post.assert_not_called()

    def test_telegram_failure_keeps_status_and_warns(self):
        from unittest import mock

        import httpx

        forbidden = httpx.Response(403, json={}, request=httpx.Request("POST", "https://x/"))
        attempts = [("confirmed", {"side_effect": httpx.ConnectError("x")}), ("delivered", {"return_value": forbidden})]
        for status, behaviour in attempts:
            with mock.patch("shops.notify.httpx.post", **behaviour):
                response = self.change(status)
            self.assertContains(response, "xabar yuborib bo&#x27;lmadi")
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, status)  # holat baribir saqlanadi

    def test_deleted_customer_or_no_token_sends_nothing(self):
        from unittest import mock

        with mock.patch("shops.notify.httpx.post") as post:
            self.shop.bot_token = ""
            self.shop.save()
            self.change("confirmed")
            self.order.customer.delete()
            self.change("delivered")
        post.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")

    def test_error_log_never_contains_token(self):
        from unittest import mock

        import httpx

        with mock.patch("shops.notify.httpx.post", side_effect=httpx.ConnectError(f"https://api.telegram.org/bot{TOKEN}/sendMessage failed")):
            with self.assertLogs("shops.notify", level="WARNING") as logs:
                self.change("confirmed")
        self.assertNotIn(TOKEN, "\n".join(logs.output))


ENV_TOKEN = "987654321:AAH-envtokenabcdefghijklmnopqrstuvw01"


class EnvTokenTests(TestCase):
    """TELEGRAM_BOT_TOKEN (.env): panel tokeni bo'lmagan bitta do'kon uchun zaxira."""

    def setUp(self):
        self.u1 = User.objects.create_user("u1", password="x12345678!")
        self.u2 = User.objects.create_user("u2", password="x12345678!")
        self.s1 = Shop.objects.create(owner=self.u1, name="Birinchi")
        self.s2 = Shop.objects.create(owner=self.u2, name="Ikkinchi")

    def test_env_token_goes_to_first_shop_without_token_only(self):
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN):
            self.assertEqual(self.s1.effective_token, ENV_TOKEN)
            self.assertEqual(self.s2.effective_token, "")
            self.assertEqual(self.s1.token_source, "env")
            self.assertTrue(self.s1.has_token)
            self.assertFalse(self.s2.has_token)

    def test_explicit_shop_id(self):
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN, TELEGRAM_BOT_SHOP_ID=self.s2.pk):
            self.assertEqual(self.s2.effective_token, ENV_TOKEN)
            self.assertEqual(self.s1.effective_token, "")

    def test_panel_token_wins_over_env(self):
        self.s1.bot_token = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
        self.s1.save()
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN):
            self.assertEqual(self.s1.effective_token, "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345")
            self.assertEqual(self.s1.token_source, "panel")
            self.assertEqual(self.s2.effective_token, ENV_TOKEN)  # env keyingi bo'sh do'konga o'tadi

    def test_same_token_saved_in_panel_disables_env(self):
        self.s2.bot_token = ENV_TOKEN
        self.s2.save()
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN):
            self.assertEqual(self.s1.effective_token, "")  # ikki do'kon bir botni tinglamasin
            self.assertEqual(self.s2.effective_token, ENV_TOKEN)

    def test_malformed_env_token_ignored(self):
        with override_settings(TELEGRAM_BOT_TOKEN="not-a-token"):
            self.assertEqual(self.s1.effective_token, "")

    def test_inactive_shop_not_chosen(self):
        Shop.objects.filter(pk=self.s1.pk).update(is_active=False)
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN):
            self.assertEqual(self.s2.effective_token, ENV_TOKEN)

    def test_env_owner_id_applies_to_env_shop_only(self):
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN, TELEGRAM_OWNER_ID=4242):
            self.assertEqual(self.s1.effective_owner_id, 4242)
            self.assertIsNone(self.s2.effective_owner_id)
        self.s1.owner_telegram_id = 99
        self.s1.save()
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN, TELEGRAM_OWNER_ID=4242):
            self.assertEqual(self.s1.effective_owner_id, 99)  # ulangan ega ustun

    def test_panel_shows_env_note_and_masks_token(self):
        self.client.login(username="u1", password="x12345678!")
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN):
            html = self.client.get(reverse("shop_settings")).content.decode()
        self.assertIn(".env", html)
        self.assertNotIn(ENV_TOKEN, html)

    def test_status_notification_uses_env_token(self):
        order = Order.objects.create(shop=self.s1, customer=Customer.objects.create(shop=self.s1, telegram_id=5), customer_name="A", phone="1", address="a", total=1)
        with override_settings(TELEGRAM_BOT_TOKEN=ENV_TOKEN), mock.patch("shops.notify.send_message", return_value=True) as send:
            notify.notify_customer_status(order, "confirmed")
        self.assertEqual(send.call_args.args[0], ENV_TOKEN)


class SecurityLayerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("sec", password="x12345678!")
        self.shop = Shop.objects.create(owner=self.user, name="S")

    def actions(self):
        return list(AuditEvent.objects.order_by("pk").values_list("action", flat=True))

    def test_login_logout_failed_are_audited_without_password(self):
        self.client.post(reverse("login"), {"username": "sec", "password": "bad-password-1"})
        self.client.post(reverse("login"), {"username": "sec", "password": "x12345678!"})
        self.client.post(reverse("logout"))
        self.assertEqual(self.actions(), ["login_failed", "login", "logout"])
        dump = " ".join(f"{e.username} {e.detail} {e.ip}" for e in AuditEvent.objects.all())
        self.assertNotIn("bad-password-1", dump)
        self.assertNotIn("x12345678!", dump)

    def test_lockout_is_audited(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "sec", "password": "bad-password-1"})
        self.client.post(reverse("login"), {"username": "sec", "password": "bad-password-1"})
        self.assertIn("login_blocked", self.actions())

    def test_token_change_is_audited_but_token_not_stored(self):
        self.client.login(username="sec", password="x12345678!")
        token = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
        self.client.post(reverse("shop_settings"), {"name": "S", "bot_token": token, "default_language": "uz", "is_active": "on"})
        self.assertIn("token_changed", self.actions())
        self.assertFalse(any(token in f"{e.detail}{e.username}" for e in AuditEvent.objects.all()))

    def test_security_page_shows_only_own_events(self):
        other = User.objects.create_user("zzz", password="x12345678!")
        AuditEvent.objects.create(user=other, username="zzz", action="password_changed", ip="9.9.9.9")
        self.client.login(username="sec", password="x12345678!")
        html = self.client.get(reverse("security")).content.decode()
        self.assertIn("Tizimga kirish", html)
        self.assertNotIn("9.9.9.9", html)

    def test_security_requires_login(self):
        self.assertEqual(self.client.get(reverse("security")).status_code, 302)
        self.assertEqual(self.client.post(reverse("revoke_sessions")).status_code, 302)

    def test_revoke_sessions_logs_out_other_devices_only(self):
        other = self.client_class()
        other.login(username="sec", password="x12345678!")
        stranger = self.client_class()
        User.objects.create_user("st", password="x12345678!")
        stranger.login(username="st", password="x12345678!")
        self.client.login(username="sec", password="x12345678!")
        self.client.post(reverse("revoke_sessions"))
        self.assertEqual(other.get(reverse("dashboard")).status_code, 302)  # chiqarildi
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)  # joriy qoldi
        self.assertEqual(stranger.get(reverse("dashboard")).status_code, 200)  # boshqa foydalanuvchi tegilmadi
        self.assertIn("sessions_revoked", self.actions())

    def test_audit_failure_never_breaks_login(self):
        with mock.patch("shops.audit.AuditEvent.objects.create", side_effect=RuntimeError("db")):
            with self.assertLogs("shops.audit", level="ERROR"):
                response = self.client.post(reverse("login"), {"username": "sec", "password": "x12345678!"})
        self.assertEqual(response.status_code, 302)


class LogRedactionTests(TestCase):
    def test_redacts_tokens_keys_and_headers(self):
        from .logsafe import MASK, redact

        token = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
        samples = [
            f"HTTP Request: POST https://api.telegram.org/bot{token}/sendMessage",
            "key AIzaSyA1234567890abcdefghijklmnopqrstuv",
            "gsk_abcdefghijklmnopqrstuvwxyz123456",
            "Authorization: Bearer abcdefghijklmnop1234",
            "api_key=supersecretvalue99 and password: hunter2hunter2",
        ]
        for text in samples:
            out = redact(text)
            self.assertIn(MASK, out)
            for leaked in (token, "AIzaSyA1234", "gsk_abcdef", "abcdefghijklmnop1234", "supersecretvalue99", "hunter2hunter2"):
                self.assertNotIn(leaked, out)

    @override_settings(GROQ_API_KEY="plain-groq-key-without-prefix")
    def test_redacts_configured_secret_exactly(self):
        from .logsafe import redact

        self.assertNotIn("plain-groq-key-without-prefix", redact("failed with plain-groq-key-without-prefix here"))

    def test_formatter_cleans_exception_traceback(self):
        import logging

        from .logsafe import RedactingFormatter

        token = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
        try:
            raise ValueError(f"bad url bot{token}")
        except ValueError:
            import sys

            record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom %s", (token,), sys.exc_info())
        out = RedactingFormatter("%(message)s").format(record)
        self.assertNotIn(token, out)

    def test_normal_text_untouched(self):
        from .logsafe import redact

        self.assertEqual(redact("Buyurtma №5 yuborildi, 14:30 da"), "Buyurtma №5 yuborildi, 14:30 da")
