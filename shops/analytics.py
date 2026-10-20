"""Boshqaruv paneli analitikasi: do'kon egasi uchun asosiy ko'rsatkichlar.

Qoidalar (aniq va izchil bo'lishi uchun):
- Barcha hisob-kitoblar faqat berilgan do'kon (shop) bo'yicha.
- Davr: oxirgi N kun, bugun ham kiradi, mahalliy vaqt (TIME_ZONE) bo'yicha kun chegaralari bilan.
- Daromad va buyurtmalar soni bekor qilingan buyurtmalarsiz hisoblanadi; bekorlar alohida ko'rsatiladi.
- Solishtirish: oldingi xuddi shuncha kunlik davr bilan (foizda). Oldingi davrda qiymat 0 bo'lsa, foiz ko'rsatilmaydi.
- Kechki xabarlar: mahalliy vaqt bilan 21:00-09:00 oralig'ida kelgan mijoz xabarlari.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.utils import timezone

from catalog.models import Product
from conversations.models import Conversation, Customer, Message
from orders.models import Order, OrderItem

ALLOWED_DAYS = (7, 30, 90)
DEFAULT_DAYS = 30
NIGHT_HOURS = frozenset(list(range(0, 9)) + list(range(21, 24)))
LOW_STOCK_THRESHOLD = 3
TOP_PRODUCTS_LIMIT = 5
STOCK_ALERTS_LIMIT = 8

CHART_W, CHART_H = 600, 160


def parse_days(raw) -> int:
    """?days= qiymatini xavfsiz tarzda tekshiradi: faqat ruxsat etilgan davrlar."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return value if value in ALLOWED_DAYS else DEFAULT_DAYS


def _aware_midnight(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


@dataclass(frozen=True)
class Period:
    days: int
    start_date: date
    end_date: date  # oxirgi kun (bugun), shu kun ham kiradi

    @property
    def start(self) -> datetime:
        return _aware_midnight(self.start_date)

    @property
    def end(self) -> datetime:  # istisno qilinadigan chegara
        return _aware_midnight(self.end_date + timedelta(days=1))

    @property
    def previous(self) -> "Period":
        return Period(self.days, self.start_date - timedelta(days=self.days), self.start_date - timedelta(days=1))

    def dates(self) -> list[date]:
        return [self.start_date + timedelta(days=i) for i in range(self.days)]


def make_period(days: int, today: date | None = None) -> Period:
    today = today or timezone.localdate()
    return Period(days, today - timedelta(days=days - 1), today)


def pct_change(current, previous) -> float | None:
    """Foizdagi o'zgarish. Oldingi qiymat 0 bo'lsa, ma'noli foiz yo'q: None."""
    if not previous:
        return None
    return round((float(current) - float(previous)) / float(previous) * 100, 1)


def short_money(value) -> str:
    """Grafik o'qlari uchun qisqa yozuv: 1 250 000 → '1.3 mln', 45 000 → '45 ming'."""
    value = Decimal(str(value))
    half_up = lambda x, exp: x.quantize(Decimal(exp), rounding=ROUND_HALF_UP)  # noqa: E731
    if value >= 1_000_000:
        return f"{half_up(value / 1_000_000, '0.1')}".rstrip("0").rstrip(".") + " mln"
    if value >= 1_000:
        return f"{half_up(value / 1_000, '1')} ming"
    return f"{half_up(value, '1')}"


def _live_orders(shop, period: Period):
    return Order.objects.filter(shop=shop, created_at__gte=period.start, created_at__lt=period.end).exclude(
        status=Order.STATUS_CANCELLED
    )


def _totals(shop, period: Period) -> dict:
    orders = _live_orders(shop, period)
    agg = orders.aggregate(count=Count("id"), revenue=Sum("total"))
    count = agg["count"] or 0
    revenue = agg["revenue"] or Decimal(0)
    messages = Message.objects.filter(
        conversation__customer__shop=shop,
        role=Message.ROLE_USER,
        created_at__gte=period.start,
        created_at__lt=period.end,
    )
    active_ids = set(messages.values_list("conversation__customer_id", flat=True).distinct())
    buyer_ids = set(orders.exclude(customer__isnull=True).values_list("customer_id", flat=True).distinct())
    return {
        "orders": count,
        "revenue": revenue,
        "avg_order": (revenue / count) if count else Decimal(0),
        "active_customers": len(active_ids),
        "buyers": len(buyer_ids & active_ids),
        "new_customers": Customer.objects.filter(shop=shop, created_at__gte=period.start, created_at__lt=period.end).count(),
        "messages": messages.count(),
    }


def _daily_series(shop, period: Period) -> dict[date, dict]:
    rows = (
        _live_orders(shop, period)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(orders=Count("id"), revenue=Sum("total"))
    )
    by_day = {r["day"]: r for r in rows}
    series = {}
    for day in period.dates():
        row = by_day.get(day)
        series[day] = {"orders": row["orders"] if row else 0, "revenue": (row["revenue"] or Decimal(0)) if row else Decimal(0)}
    return series


def _revenue_bars(series: dict[date, dict]) -> dict:
    """SVG ustunli grafik uchun tayyor geometriya (raqamlar, matnlar shablonda avtomatik escape qilinadi)."""
    days = list(series)
    peak = max((float(v["revenue"]) for v in series.values()), default=0.0)
    n = len(days)
    slot = CHART_W / n
    width = max(slot * 0.7, 1.5)
    bars = []
    for i, day in enumerate(days):
        revenue = float(series[day]["revenue"])
        height = (revenue / peak * (CHART_H - 8)) if peak else 0
        if revenue == 0:
            height = 2  # bo'sh kun ham ko'rinsin
        bars.append(
            {
                "zero": revenue == 0,
                "x": round(i * slot + (slot - width) / 2, 2),
                "y": round(CHART_H - height, 2),
                "w": round(width, 2),
                "h": round(height, 2),
                "label": day.strftime("%d.%m"),
                "orders": series[day]["orders"],
                "revenue": int(revenue),
            }
        )
    return {
        "bars": bars,
        "peak": short_money(peak) if peak else "0",
        "first": days[0].strftime("%d.%m"),
        "middle": days[n // 2].strftime("%d.%m"),
        "last": days[-1].strftime("%d.%m"),
        "empty": peak == 0,
        "w": CHART_W,
        "h": CHART_H,
    }


def _hour_bars(shop, period: Period) -> dict:
    rows = (
        Message.objects.filter(
            conversation__customer__shop=shop,
            role=Message.ROLE_USER,
            created_at__gte=period.start,
            created_at__lt=period.end,
        )
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(n=Count("id"))
    )
    counts = [0] * 24
    for row in rows:
        counts[row["hour"]] = row["n"]
    total = sum(counts)
    night = sum(c for h, c in enumerate(counts) if h in NIGHT_HOURS)
    peak = max(counts) if counts else 0
    slot = CHART_W / 24
    bars = []
    for hour, count in enumerate(counts):
        height = (count / peak * (CHART_H - 8)) if peak else 0
        bars.append(
            {
                "x": round(hour * slot + 2, 2),
                "y": round(CHART_H - height, 2),
                "w": round(slot - 4, 2),
                "h": round(height, 2),
                "hour": f"{hour:02d}:00",
                "count": count,
                "night": hour in NIGHT_HOURS,
            }
        )
    return {
        "bars": bars,
        "total": total,
        "night": night,
        "night_pct": round(night / total * 100) if total else None,
        "empty": total == 0,
        "w": CHART_W,
        "h": CHART_H,
    }


def _status_breakdown(shop, period: Period) -> list[dict]:
    rows = (
        Order.objects.filter(shop=shop, created_at__gte=period.start, created_at__lt=period.end)
        .values("status")
        .annotate(n=Count("id"))
    )
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    result = []
    offset = 0.0
    for value, label in Order.STATUS_CHOICES:
        n = counts.get(value, 0)
        width = (n / total * 100) if total else 0.0
        result.append(
            {"status": value, "label": label, "count": n, "pct": round(width), "x": round(offset, 2), "w": round(width, 2)}
        )
        offset += width
    return result


def _top_products(shop, period: Period) -> list[dict]:
    revenue = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=18, decimal_places=0))
    rows = (
        OrderItem.objects.filter(
            order__shop=shop,
            order__created_at__gte=period.start,
            order__created_at__lt=period.end,
        )
        .exclude(order__status=Order.STATUS_CANCELLED)
        .values("name")
        .annotate(qty=Sum("quantity"), revenue=Sum(revenue))
        .order_by("-revenue", "name")[:TOP_PRODUCTS_LIMIT]
    )
    rows = list(rows)
    peak = max((float(r["revenue"]) for r in rows), default=0)
    return [
        {
            "name": r["name"],
            "qty": r["qty"],
            "revenue": r["revenue"],
            "share": round(float(r["revenue"]) / peak * 100) if peak else 0,
        }
        for r in rows
    ]


def _stock_alerts(shop) -> dict:
    low = Product.objects.filter(shop=shop, is_active=True, stock__lte=LOW_STOCK_THRESHOLD)
    return {
        "out_count": low.filter(stock=0).count(),
        "low_count": low.filter(stock__gt=0).count(),
        "items": list(low.order_by("stock", "name")[:STOCK_ALERTS_LIMIT]),
        "threshold": LOW_STOCK_THRESHOLD,
    }


def build_dashboard(shop, days: int, today: date | None = None) -> dict:
    period = make_period(days, today)
    current = _totals(shop, period)
    previous = _totals(shop, period.previous)
    series = _daily_series(shop, period)
    cancelled = Order.objects.filter(
        shop=shop, status=Order.STATUS_CANCELLED, created_at__gte=period.start, created_at__lt=period.end
    ).count()
    active = current["active_customers"]
    statuses = _status_breakdown(shop, period)
    return {
        "days": days,
        "allowed_days": ALLOWED_DAYS,
        "period_label": f"{period.start_date.strftime('%d.%m.%Y')} — {period.end_date.strftime('%d.%m.%Y')}",
        "totals": current,
        "deltas": {
            "orders": pct_change(current["orders"], previous["orders"]),
            "revenue": pct_change(current["revenue"], previous["revenue"]),
            "active_customers": pct_change(current["active_customers"], previous["active_customers"]),
        },
        "conversion_pct": round(current["buyers"] / active * 100, 1) if active else None,
        "cancelled": cancelled,
        "chart": _revenue_bars(series),
        "hours": _hour_bars(shop, period),
        "statuses": statuses,
        "top_products": _top_products(shop, period),
        "stock": _stock_alerts(shop),
        "attention": Conversation.objects.filter(customer__shop=shop, needs_attention=True).count(),
        "has_orders_in_period": any(st["count"] for st in statuses),
    }
