"""Buyurtma holati oqimi: o'tish qoidalari, ombor qoldig'ini qaytarish, tarix, panel tugmalari."""
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product
from conversations.models import Customer
from shops.models import Shop

from . import services
from .models import Order, OrderItem, OrderStatusLog


def make_order(shop, stock_left=8, qty=2, status=Order.STATUS_NEW, customer=None):
    product = Product.objects.create(shop=shop, name="Ko'ylak", price=100000, stock=stock_left)
    order = Order.objects.create(shop=shop, customer=customer, customer_name="Ali", phone="+998901112233", address="Toshkent", total=100000 * qty, status=status)
    OrderItem.objects.create(order=order, product=product, name=product.name, unit_price=product.price, quantity=qty)
    return order, product


class ServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a", password="x12345678!")
        self.shop = Shop.objects.create(owner=self.user, name="D")

    def test_allowed_next_flow(self):
        self.assertEqual(services.allowed_next("new"), ["confirmed", "shipped", "delivered", "cancelled"])
        self.assertEqual(services.allowed_next("confirmed"), ["shipped", "delivered", "cancelled"])
        self.assertEqual(services.allowed_next("shipped"), ["delivered", "cancelled"])
        self.assertEqual(services.allowed_next("delivered"), [])
        self.assertEqual(services.allowed_next("cancelled"), [])

    def test_full_path_logs_each_step(self):
        order, _ = make_order(self.shop)
        for status in ("confirmed", "shipped", "delivered"):
            self.assertTrue(services.change_status(order, status))
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")
        self.assertEqual(
            list(order.status_log.values_list("from_status", "to_status")),
            [("new", "confirmed"), ("confirmed", "shipped"), ("shipped", "delivered")],
        )

    def test_same_status_is_noop_without_log(self):
        order, _ = make_order(self.shop)
        self.assertFalse(services.change_status(order, "new"))
        self.assertEqual(OrderStatusLog.objects.count(), 0)

    def test_final_states_are_locked(self):
        for final in ("delivered", "cancelled"):
            order, _ = make_order(self.shop, status=final)
            for target in ("new", "confirmed", "shipped", "delivered", "cancelled"):
                if target == final:
                    continue
                with self.assertRaises(services.InvalidTransition):
                    services.change_status(order, target)

    def test_no_going_backwards(self):
        order, _ = make_order(self.shop, status="shipped")
        for target in ("new", "confirmed"):
            with self.assertRaises(services.InvalidTransition):
                services.change_status(order, target)

    def test_cancel_restores_stock_once(self):
        order, product = make_order(self.shop, stock_left=8, qty=2)
        services.change_status(order, "cancelled")
        product.refresh_from_db()
        self.assertEqual(product.stock, 10)
        stale = Order.objects.get(pk=order.pk)
        stale.status = "new"  # eskirgan nusxa (ikkinchi oyna): qayta bekor qilish qoldiqni oshirmaydi
        self.assertFalse(services.change_status(stale, "cancelled"))
        product.refresh_from_db()
        self.assertEqual(product.stock, 10)

    def test_delivered_does_not_touch_stock(self):
        order, product = make_order(self.shop, stock_left=8, qty=2)
        services.change_status(order, "delivered")
        product.refresh_from_db()
        self.assertEqual(product.stock, 8)

    def test_cancel_with_deleted_product_does_not_crash(self):
        order, product = make_order(self.shop)
        product.delete()
        self.assertTrue(services.change_status(order, "cancelled"))


class PanelFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a", password="x12345678!")
        self.shop = Shop.objects.create(owner=self.user, name="D")
        self.client.login(username="a", password="x12345678!")
        self.order, self.product = make_order(self.shop)

    def post(self, status, **extra):
        return self.client.post(reverse("order_status", args=[self.order.pk]), {"status": status, **extra}, follow=True)

    def test_detail_shows_only_valid_actions(self):
        html = self.client.get(reverse("order_detail", args=[self.order.pk])).content.decode()
        for label in ("Qabul qilish", "Yuborildi deb belgilash", "Yetkazildi deb belgilash", "Bekor qilish"):
            self.assertIn(label, html)
        services.change_status(self.order, "shipped")
        html = self.client.get(reverse("order_detail", args=[self.order.pk])).content.decode()
        self.assertNotIn("Qabul qilish", html)
        self.assertIn("Yetkazildi deb belgilash", html)

    def test_finished_order_has_no_buttons(self):
        services.change_status(self.order, "delivered")
        html = self.client.get(reverse("order_detail", args=[self.order.pk])).content.decode()
        self.assertIn("yakunlangan", html)
        self.assertNotIn('name="status"', html)

    def test_ship_then_history_visible(self):
        self.post("shipped")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")
        html = self.client.get(reverse("order_detail", args=[self.order.pk])).content.decode()
        self.assertIn("Tarix", html)
        self.assertIn("Yangi → <strong>Yuborildi</strong>", html)

    def test_cancel_via_panel_restores_stock_and_message(self):
        response = self.post("cancelled")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertContains(response, "qaytarildi")

    def test_invalid_transition_is_rejected_with_message(self):
        services.change_status(self.order, "cancelled")
        response = self.post("confirmed")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertContains(response, "bo&#x27;lmaydi")

    def test_shipped_notifies_customer_in_their_language(self):
        customer = Customer.objects.create(shop=self.shop, telegram_id=777, language="ru")
        self.order.customer = customer
        self.order.save()
        self.shop.bot_token = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
        self.shop.save()
        with mock.patch("shops.notify.send_message", return_value=True) as send:
            self.post("shipped", notify="on")
        self.assertIn("отправлен", send.call_args.args[2])

    def test_tabs_show_counts_and_filter(self):
        make_order(self.shop, status="shipped")
        html = self.client.get(reverse("orders")).content.decode()
        self.assertIn("Yuborildi <span", html)
        filtered = self.client.get(reverse("orders") + "?status=shipped").content.decode()
        self.assertIn("#" + str(Order.objects.get(status="shipped").pk), filtered)
        self.assertNotIn(f"#{self.order.pk}<", filtered)

    def test_sidebar_badge_counts_only_new_orders_of_own_shop(self):
        other = Shop.objects.create(owner=User.objects.create_user("b", password="x12345678!"), name="E")
        make_order(other)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('class="count" title="Yangi buyurtmalar">1<', html)
        services.change_status(self.order, "confirmed")
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn('class="count"', html)

    def test_other_shop_cannot_change_status(self):
        User.objects.create_user("b", password="x12345678!")
        Shop.objects.create(owner=User.objects.get(username="b"), name="E")
        self.client.logout()
        self.client.login(username="b", password="x12345678!")
        self.assertEqual(self.post("cancelled").status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")
