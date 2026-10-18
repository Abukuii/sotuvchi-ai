from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from catalog.importer import build_template_xlsx
from catalog.models import Product
from conversations.models import Conversation, Customer
from orders.models import Order

from .models import Shop

PASSWORD = "S3cure-pass-123"
TOKEN = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"


def make_user(name):
    user = User.objects.create_user(name, password=PASSWORD)
    shop = Shop.objects.create(owner=user, name=f"{name} do'koni")
    return user, shop


class AuthTests(TestCase):
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


class SettingsTests(TestCase):
    def setUp(self):
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


class CatalogViewTests(TestCase):
    def setUp(self):
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


class TenantIsolationTests(TestCase):
    def setUp(self):
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


class OrderViewTests(TestCase):
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

