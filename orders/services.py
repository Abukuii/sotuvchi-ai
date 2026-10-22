"""Buyurtma holatini o'zgartirish — yagona joy (panel ham, Telegram tugmalari ham shu orqali ishlaydi).

Oqim:  Yangi → Qabul qilindi → Yuborildi → Yetkazildi.  Bekor qilish: Yangi/Qabul/Yuborildi dan.
Oraliq bosqichni o'tkazib yuborish mumkin (masalan, Yangi → Yuborildi). Yetkazildi va Bekor qilindi — yakuniy:
undan keyin o'zgartirib bo'lmaydi. Bekor qilinsa, ombordan ayirilgan mahsulotlar qoldig'i qaytariladi.
"""
from django.db import transaction
from django.db.models import F

from catalog.models import Product

from .models import Order, OrderStatusLog

S = Order
FLOW = [S.STATUS_NEW, S.STATUS_CONFIRMED, S.STATUS_SHIPPED, S.STATUS_DELIVERED]
FINAL = {S.STATUS_DELIVERED, S.STATUS_CANCELLED}


class InvalidTransition(Exception):
    pass


def allowed_next(status: str) -> list[str]:
    """Berilgan holatdan o'tish mumkin bo'lgan holatlar (tartib bilan; bekor qilish oxirida)."""
    if status in FINAL or status not in FLOW:
        return []
    forward = FLOW[FLOW.index(status) + 1 :]
    return forward + [S.STATUS_CANCELLED]


def change_status(order: Order, new_status: str, source: str = OrderStatusLog.SOURCE_PANEL) -> bool:
    """Holatni o'zgartiradi. True — o'zgardi, False — allaqachon shu holatda. Noto'g'ri o'tishda InvalidTransition.

    Qator qulflanadi: panel va bot bir vaqtda bosilsa ham qoldiq ikki marta qaytarilmaydi.
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == new_status:
            order.status = locked.status
            return False
        if new_status not in allowed_next(locked.status):
            raise InvalidTransition(f"{locked.status} → {new_status}")
        previous = locked.status
        if new_status == S.STATUS_CANCELLED:
            for item in locked.items.all():
                if item.product_id:
                    Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
        locked.status = new_status
        locked.save(update_fields=["status"])
        OrderStatusLog.objects.create(order=locked, from_status=previous, to_status=new_status, source=source)
    order.status = new_status
    return True
