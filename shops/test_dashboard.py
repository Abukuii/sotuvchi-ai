"""Analitika (aniq raqamlar), xavfsizlik sarlavhalari, parol almashtirish va rang palitrasi testlari."""
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from conversations.models import Conversation, Customer, Message
from orders.models import Order, OrderItem

from . import analytics
from .tests import PASSWORD, BaseTestCase, make_user

TODAY = date(2026, 6, 15)


def local(y, m, d, h=12, mi=0):
    return timezone.make_aware(datetime(y, m, d, h, mi))


def make_order(shop, when, total, status="new", customer=None, items=()):
    order = Order.objects.create(
        shop=shop, customer=customer, customer_name="Ali", phone="+998901112233", address="Jizzax", total=total, status=status
    )
    Order.objects.filter(pk=order.pk).update(created_at=when)
    for name, price, qty in items:
        OrderItem.objects.create(order=order, name=name, unit_price=price, quantity=qty)
    return order


def make_message(shop, tg, when, text="salom", role="user"):
    customer, _ = Customer.objects.get_or_create(shop=shop, telegram_id=tg)
    conv, _ = Conversation.objects.get_or_create(customer=customer)
    msg = Message.objects.create(conversation=conv, role=role, text=text)
    Message.objects.filter(pk=msg.pk).update(created_at=when)
    return customer


class AnalyticsTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.shop = make_user("owner")

    def build(self, days=30):
        return analytics.build_dashboard(self.shop, days, today=TODAY)

    def test_empty_shop(self):
        data = self.build()
        self.assertEqual(data["totals"]["orders"], 0)
        self.assertEqual(data["totals"]["revenue"], 0)
        self.assertIsNone(data["conversion_pct"])
        self.assertIsNone(data["hours"]["night_pct"])
        self.assertTrue(data["chart"]["empty"])
        self.assertEqual(len(data["chart"]["bars"]), 30)
        self.assertFalse(data["has_orders_in_period"])

    def test_revenue_orders_and_average_exclude_cancelled(self):
        make_order(self.shop, local(2026, 6, 15), 100000)
        make_order(self.shop, local(2026, 6, 10), 300000, status="delivered")
        make_order(self.shop, local(2026, 6, 10), 999999, status="cancelled")
        data = self.build()
        self.assertEqual(data["totals"]["orders"], 2)
        self.assertEqual(data["totals"]["revenue"], 400000)
        self.assertEqual(data["totals"]["avg_order"], 200000)
        self.assertEqual(data["cancelled"], 1)

    def test_period_boundaries_use_local_midnight(self):
        # 7 kunlik davr: 09.06 00:00 dan 15.06 23:59 gacha (Asia/Tashkent)
        make_order(self.shop, local(2026, 6, 9, 0, 0), 1000)  # birinchi daqiqa: kiradi
        make_order(self.shop, local(2026, 6, 8, 23, 59), 5000)  # bir daqiqa oldin: kirmaydi
        make_order(self.shop, local(2026, 6, 15, 23, 30), 2000)  # kechki buyurtma: bugunga kiradi
        make_order(self.shop, local(2026, 6, 16, 0, 0), 7000)  # ertasi kun: kirmaydi
        data = self.build(7)
        self.assertEqual(data["totals"]["revenue"], 3000)
        bars = data["chart"]["bars"]
        self.assertEqual(bars[0]["revenue"], 1000)
        self.assertEqual(bars[-1]["revenue"], 2000)  # kechki buyurtma to'g'ri kunda

    def test_delta_against_previous_period(self):
        make_order(self.shop, local(2026, 6, 14), 150000)  # joriy 7 kun
        make_order(self.shop, local(2026, 6, 5), 100000)  # oldingi 7 kun (02.06–08.06)
        data = self.build(7)
        self.assertEqual(data["deltas"]["revenue"], 50.0)
        self.assertEqual(data["deltas"]["orders"], 0.0)

    def test_delta_is_none_when_previous_is_zero(self):
        make_order(self.shop, local(2026, 6, 14), 150000)
        self.assertIsNone(self.build(7)["deltas"]["revenue"])

    def test_conversion_and_customers(self):
        a = make_message(self.shop, 1, local(2026, 6, 14, 10))
        make_message(self.shop, 2, local(2026, 6, 14, 11))
        make_message(self.shop, 3, local(2026, 6, 14, 12))
        make_message(self.shop, 4, local(2026, 6, 14, 13))
        make_order(self.shop, local(2026, 6, 14, 14), 1000, customer=a)
        make_message(self.shop, 5, local(2026, 3, 1))  # davrdan tashqarida
        data = self.build(7)
        self.assertEqual(data["totals"]["active_customers"], 4)
        self.assertEqual(data["totals"]["buyers"], 1)
        self.assertEqual(data["conversion_pct"], 25.0)

    def test_assistant_messages_not_counted_as_customer_activity(self):
        make_message(self.shop, 1, local(2026, 6, 14, 10), role="assistant")
        data = self.build(7)
        self.assertEqual(data["totals"]["active_customers"], 0)
        self.assertEqual(data["hours"]["total"], 0)

    def test_night_messages_share(self):
        for hour in (22, 23, 3, 8):  # tun (kechki 21–09)
            make_message(self.shop, hour, local(2026, 6, 14, hour))
        for hour in (9, 12, 20, 21 - 1):  # kunduz
            make_message(self.shop, 100 + hour, local(2026, 6, 14, hour, 30))
        data = self.build(7)["hours"]
        self.assertEqual(data["total"], 8)
        self.assertEqual(data["night"], 4)
        self.assertEqual(data["night_pct"], 50)
        night_hours = {b["hour"] for b in data["bars"] if b["night"]}
        self.assertIn("21:00", night_hours)
        self.assertIn("08:00", night_hours)
        self.assertNotIn("09:00", night_hours)
        self.assertNotIn("20:00", night_hours)

    def test_top_products_ranked_by_revenue(self):
        make_order(self.shop, local(2026, 6, 14), 0, items=[("Ko'ylak", 100000, 2), ("Krossovka", 500000, 1)])
        make_order(self.shop, local(2026, 6, 13), 0, items=[("Ko'ylak", 100000, 1)], status="cancelled")
        top = self.build(7)["top_products"]
        self.assertEqual([p["name"] for p in top], ["Krossovka", "Ko'ylak"])
        self.assertEqual(top[0]["revenue"], 500000)
        self.assertEqual(top[1]["qty"], 2)  # bekor qilingan hisobga olinmaydi
        self.assertEqual(top[0]["share"], 100)
        self.assertEqual(top[1]["share"], 40)

    def test_status_breakdown_geometry(self):
        make_order(self.shop, local(2026, 6, 14), 1, status="new")
        make_order(self.shop, local(2026, 6, 14), 1, status="delivered")
        make_order(self.shop, local(2026, 6, 14), 1, status="delivered")
        make_order(self.shop, local(2026, 6, 14), 1, status="cancelled")
        statuses = {s["status"]: s for s in self.build(7)["statuses"]}
        self.assertEqual(statuses["delivered"]["count"], 2)
        self.assertEqual(statuses["delivered"]["pct"], 50)
        widths = sum(s["w"] for s in statuses.values())
        self.assertAlmostEqual(widths, 100, delta=0.05)

    def test_stock_alerts(self):
        Product.objects.create(shop=self.shop, name="Tugagan", price=1, stock=0)
        Product.objects.create(shop=self.shop, name="Kam", price=1, stock=2)
        Product.objects.create(shop=self.shop, name="Yetarli", price=1, stock=50)
        Product.objects.create(shop=self.shop, name="Nofaol", price=1, stock=0, is_active=False)
        stock = self.build()["stock"]
        self.assertEqual(stock["out_count"], 1)
        self.assertEqual(stock["low_count"], 1)
        self.assertEqual([p.name for p in stock["items"]], ["Tugagan", "Kam"])

    def test_other_shops_data_is_isolated(self):
        _, other = make_user("other")
        make_order(other, local(2026, 6, 14), 777000)
        make_message(other, 9, local(2026, 6, 14))
        Product.objects.create(shop=other, name="Boshqa", price=1, stock=0)
        data = self.build(7)
        self.assertEqual(data["totals"]["revenue"], 0)
        self.assertEqual(data["totals"]["active_customers"], 0)
        self.assertEqual(data["stock"]["items"], [])

    def test_parse_days_whitelist(self):
        self.assertEqual(analytics.parse_days("7"), 7)
        self.assertEqual(analytics.parse_days("90"), 90)
        for bad in (None, "", "abc", "-5", "0", "1000000", "30; DROP", "7.5"):
            self.assertEqual(analytics.parse_days(bad), 30, bad)

    def test_pct_change_and_short_money(self):
        self.assertEqual(analytics.pct_change(50, 100), -50.0)
        self.assertIsNone(analytics.pct_change(5, 0))
        self.assertEqual(analytics.short_money(1250000), "1.3 mln")
        self.assertEqual(analytics.short_money(45000), "45 ming")
        self.assertEqual(analytics.short_money(900), "900")

    def test_chart_bars_fit_in_viewbox(self):
        make_order(self.shop, local(2026, 6, 14), 500)
        for bar in self.build(7)["chart"]["bars"]:
            self.assertGreaterEqual(bar["y"], 0)
            self.assertLessEqual(bar["y"] + bar["h"], analytics.CHART_H + 0.01)


class DashboardViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.shop = make_user("owner")
        self.client.login(username="owner", password=PASSWORD)

    def test_renders_empty_and_all_periods(self):
        for days in ("7", "30", "90", "bad", "99999"):
            response = self.client.get(reverse("dashboard"), {"days": days})
            self.assertEqual(response.status_code, 200, days)
            self.assertContains(response, "Daromad")

    def test_shows_real_numbers(self):
        now = timezone.now()
        order = make_order(self.shop, now, 250000, items=[("Ko'ylak", 125000, 2)])
        response = self.client.get(reverse("dashboard"), {"days": 7})
        self.assertContains(response, "250\u00a0000")
        self.assertContains(response, "Ko&#x27;ylak")
        self.assertContains(response, f"#{order.pk}")

    def test_svg_numbers_use_dot_decimal_separator(self):
        make_order(self.shop, timezone.now(), 1000)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIsNone(re.search(r'(x|y|width|height)="\d+,\d+"', html))

    def test_product_name_is_escaped(self):
        make_order(self.shop, timezone.now(), 1000, items=[("<script>alert(1)</script>", 1000, 1)])
        Product.objects.create(shop=self.shop, name="<img src=x onerror=alert(2)>", price=1, stock=0)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_other_shop_revenue_not_visible(self):
        _, other = make_user("other")
        make_order(other, timezone.now(), 987654321)
        self.assertNotContains(self.client.get(reverse("dashboard")), "987\u00a0654")

    def test_dashboard_has_no_inline_styles_or_handlers(self):
        make_order(self.shop, timezone.now(), 1000, items=[("Test", 1000, 1)])
        for name in ["dashboard", "catalog", "orders", "conversations", "shop_settings", "password_change"]:
            html = self.client.get(reverse(name)).content.decode()
            self.assertIsNone(re.search(r"\sstyle=", html), name)
            self.assertIsNone(re.search(r"\son[a-z]+=", html, re.I), name)
            self.assertNotIn("<style", html, name)


class SecurityHeaderTests(BaseTestCase):
    def test_csp_on_panel_not_admin(self):
        response = self.client.get(reverse("login"))
        csp = response["Content-Security-Policy"]
        for part in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "form-action 'self'"):
            self.assertIn(part, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("Content-Security-Policy", self.client.get("/admin/login/"))
        self.assertIn("camera=()", response["Permissions-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_authenticated_pages_not_cached(self):
        make_user("owner")
        self.client.login(username="owner", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("dashboard"))["Cache-Control"], "no-store")


class PasswordChangeTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        make_user("owner")

    def test_requires_login(self):
        self.assertEqual(self.client.get(reverse("password_change")).status_code, 302)

    def test_change_password_keeps_session(self):
        self.client.login(username="owner", password=PASSWORD)
        response = self.client.post(
            reverse("password_change"),
            {"old_password": PASSWORD, "new_password1": "Yangi-parol-9876", "new_password2": "Yangi-parol-9876"},
        )
        self.assertRedirects(response, reverse("shop_settings"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertTrue(User.objects.get(username="owner").check_password("Yangi-parol-9876"))

    def test_wrong_old_or_weak_password_rejected(self):
        self.client.login(username="owner", password=PASSWORD)
        self.client.post(reverse("password_change"), {"old_password": "xato", "new_password1": "Yangi-parol-9876", "new_password2": "Yangi-parol-9876"})
        self.client.post(reverse("password_change"), {"old_password": PASSWORD, "new_password1": "12345678", "new_password2": "12345678"})
        self.assertTrue(User.objects.get(username="owner").check_password(PASSWORD))


class PalettePolicyTests(TestCase):
    """Interfeys faqat qora/oq (neytral) va xakki-zaytun (yashil-sariq oralig'i) ranglaridan iborat bo'lishi kerak."""

    HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

    @staticmethod
    def allowed(r, g, b):
        import colorsys

        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn <= 12:  # neytral: oq/kulrang/qora
            return True
        hue = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
        return 60 <= hue <= 150  # xakki/zaytun/yashil; qizil, ko'k, binafsha, to'q sariq emas

    def css(self):
        return (Path(settings.BASE_DIR) / "static" / "style.css").read_text()

    def test_all_css_colors_are_neutral_or_khaki_green(self):
        bad = []
        for m in self.HEX.finditer(self.css()):
            h = m.group(1)
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
            if not self.allowed(r, g, b):
                bad.append(m.group(0))
        self.assertEqual(bad, [])

    def test_pure_white_is_not_used(self):
        """Oq rang xiralashtirilgan: toza #fff/#ffffff fon va matn sifatida ishlatilmaydi."""
        self.assertNotRegex(self.css(), r"#(?:fff|ffffff)\b(?![0-9a-fA-F])")

    def test_policy_rejects_other_hues(self):
        for r, g, b in ((200, 30, 30), (30, 60, 200), (220, 140, 20), (140, 40, 160)):
            self.assertFalse(self.allowed(r, g, b))
        for r, g, b in ((169, 182, 101), (95, 111, 45), (20, 20, 20), (240, 240, 236)):
            self.assertTrue(self.allowed(r, g, b))

    def test_no_other_color_notations_or_names(self):
        css = self.css()
        self.assertNotRegex(css, r"\b(rgb|rgba|hsl|hsla)\(")
        for name in ("red", "blue", "orange", "yellow", "purple", "pink", "crimson", "teal", "gold", "indigo"):
            self.assertNotRegex(css, rf"[:\s]{name}\b", name)

    def test_templates_have_no_color_literals(self):
        root = Path(settings.BASE_DIR) / "templates"
        for path in root.rglob("*.html"):
            text = path.read_text()
            self.assertIsNone(self.HEX.search(text), path.name)
            self.assertIsNone(re.search(r"[\U0001F300-\U0001FAFF\u2705\u274C\u2B1C\u26A0]", text), f"emoji in {path.name}")


class LandingTests(BaseTestCase):
    def test_public_landing_for_anonymous(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bot sotdi")
        self.assertContains(response, reverse("signup"))
        self.assertNotContains(response, "Chiqish")

    def test_landing_for_logged_in_links_to_panel(self):
        make_user("owner")
        self.client.login(username="owner", password=PASSWORD)
        response = self.client.get("/")
        self.assertContains(response, reverse("dashboard"))
        self.assertNotContains(response, "Bepul boshlash")

    def test_panel_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_landing_has_no_inline_styles_scripts_or_emoji(self):
        html = self.client.get("/").content.decode()
        self.assertIsNone(re.search(r"\sstyle=", html))
        self.assertNotIn("<script", html.replace('<script src="/static/app.js" defer></script>', ""))
        self.assertEqual(self.client.get("/")["Content-Security-Policy"].count("unsafe-inline"), 0)


class SidebarTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        make_user("owner")
        self.client.login(username="owner", password=PASSWORD)

    def test_panel_pages_have_sidebar_with_collapse_toggle(self):
        for name in ["dashboard", "catalog", "orders", "conversations", "shop_settings", "password_change"]:
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn('id="sidebar"', html, name)
            self.assertIn("data-sidebar-toggle", html, name)
            self.assertIn('aria-controls="sidebar"', html, name)
            self.assertIn("data-sidebar-open", html, name)  # telefondagi menyu tugmasi
            self.assertNotIn('class="topbar"', html, name)
            self.assertEqual(html.count("<main"), 1, name)

    def test_active_link_is_marked(self):
        html = self.client.get(reverse("catalog")).content.decode()
        self.assertRegex(html, r'href="/catalog/"[^>]*class="active"')
        self.assertNotRegex(html, r'href="/orders/"[^>]*class="active"')

    def test_logout_is_post_form_with_csrf(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertRegex(html, r'<form method="post" action="/logout/">\s*<input type="hidden" name="csrfmiddlewaretoken"')

    def test_login_and_signup_use_public_header_without_sidebar(self):
        self.client.logout()
        for name in ["login", "signup"]:
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotIn('id="sidebar"', html)
            self.assertIn('class="topbar"', html)

    def test_logged_in_landing_uses_public_header(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn('id="sidebar"', html)
        self.assertIn("Panelga o'tish", html)

    def test_sidebar_script_and_css_are_wired(self):
        self.assertIn("sidebar-collapsed", (Path(settings.BASE_DIR) / "static" / "app.js").read_text())
        css = (Path(settings.BASE_DIR) / "static" / "style.css").read_text()
        for needle in ("body.sb-collapsed", "body.sb-open", "@media (max-width: 860px)"):
            self.assertIn(needle, css)

    def test_charts_are_compact(self):
        self.assertLessEqual(analytics.CHART_H, 110)
