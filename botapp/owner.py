"""Do'kon egasi uchun buyurtma tugmalari (Telegramda): Qabul qilish / Yuborildi / Yetkazildi / Bekor qilish.

Tugma ma'lumoti: "o:<buyurtma_id>:<amal>". Faqat do'konga ulangan egasi (owner_telegram_id) bosa oladi;
buyurtma shu do'konniki bo'lishi shart. Holat o'zgarishi panel bilan bir xil servis orqali bajariladi.
"""
from dataclasses import dataclass, field

from orders import services
from orders.models import Order, OrderStatusLog
from shops import notify
from shops.models import Shop

ACTIONS = {
    "ok": Order.STATUS_CONFIRMED,
    "sh": Order.STATUS_SHIPPED,
    "dl": Order.STATUS_DELIVERED,
    "no": Order.STATUS_CANCELLED,
}
CODE_OF = {v: k for k, v in ACTIONS.items()}

TEXTS = {
    "uz": {
        "labels": {"ok": "✅ Qabul qilish", "sh": "📦 Yuborildi", "dl": "🚚 Yetkazildi", "no": "✖️ Bekor qilish"},
        "status": {"new": "Yangi", "confirmed": "Qabul qilindi", "shipped": "Yuborildi", "delivered": "Yetkazildi", "cancelled": "Bekor qilindi"},
        "now": "Holat",
        "denied": "Bu tugma faqat do'kon egasi uchun.",
        "missing": "Buyurtma topilmadi.",
        "invalid": "Bu holatga o'tkazib bo'lmaydi.",
        "done": "Holat: {status}",
    },
    "ru": {
        "labels": {"ok": "✅ Принять", "sh": "📦 Отправлен", "dl": "🚚 Доставлен", "no": "✖️ Отменить"},
        "status": {"new": "Новый", "confirmed": "Принят", "shipped": "Отправлен", "delivered": "Доставлен", "cancelled": "Отменён"},
        "now": "Статус",
        "denied": "Эта кнопка только для владельца магазина.",
        "missing": "Заказ не найден.",
        "invalid": "Нельзя перевести в этот статус.",
        "done": "Статус: {status}",
    },
}


def _t(shop: Shop) -> dict:
    return TEXTS.get(shop.default_language, TEXTS["uz"])


def order_rows(shop: Shop, order_id: int, status: str) -> list[list[tuple[str, str]]]:
    """Joriy holatdan mumkin bo'lgan amallar tugmalari (yakuniy holatda — bo'sh)."""
    t = _t(shop)
    codes = [CODE_OF[s] for s in services.allowed_next(status)]
    buttons = [(t["labels"][c], f"o:{order_id}:{c}") for c in codes]
    return [buttons[:2], buttons[2:]] if len(buttons) > 2 else ([buttons] if buttons else [])


@dataclass
class OwnerResult:
    toast: str = ""
    text_suffix: str = ""  # egasining xabari oxiriga qo'shiladigan holat qatori
    rows: list = field(default_factory=list)
    changed: bool = False
    customer_chat_id: int | None = None
    customer_text: str | None = None
    refresh: bool = False  # egasining xabarini yangilash kerakmi


def handle_action(shop: Shop, user_id: int, data: str) -> OwnerResult:
    t = _t(shop)
    owner_id = shop.effective_owner_id
    if not owner_id or user_id != owner_id:
        return OwnerResult(toast=t["denied"])
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "o" or not parts[1].isdigit() or parts[2] not in ACTIONS:
        return OwnerResult(toast=t["missing"])
    order = Order.objects.select_related("customer", "shop").filter(pk=int(parts[1]), shop=shop).first()
    if order is None:
        return OwnerResult(toast=t["missing"])
    new_status = ACTIONS[parts[2]]
    try:
        changed = services.change_status(order, new_status, source=OrderStatusLog.SOURCE_BOT)
    except services.InvalidTransition:
        # Eskirgan tugma (panelda allaqachon o'zgargan): joriy holat va to'g'ri tugmalarni ko'rsatamiz
        return OwnerResult(
            toast=t["invalid"],
            text_suffix=_suffix(t, order.status),
            rows=order_rows(shop, order.pk, order.status),
            refresh=True,
        )
    result = OwnerResult(
        toast=t["done"].format(status=t["status"][order.status]),
        text_suffix=_suffix(t, order.status),
        rows=order_rows(shop, order.pk, order.status),
        changed=changed,
        refresh=True,
    )
    if changed and order.customer is not None:
        text = notify.status_text(order, new_status)
        if text:
            result.customer_chat_id = order.customer.telegram_id
            result.customer_text = text
    return result


def _suffix(t: dict, status: str) -> str:
    return f"\n\n{t['now']}: {t['status'].get(status, status)}"


def strip_status(text: str) -> str:
    """Egasi xabaridan oxirgi "Holat: ..." qatorini olib tashlaydi (qayta yangilashda takrorlanmasin)."""
    head, sep, tail = text.rpartition("\n\n")
    if sep and any(tail.startswith(f"{t['now']}: ") for t in TEXTS.values()):
        return head
    return text
