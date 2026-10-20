from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from catalog.importer import build_template_xlsx
from catalog.models import Product
from conversations.models import Conversation, Customer
from orders.models import Order

from . import crypto
from .models import Shop

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
