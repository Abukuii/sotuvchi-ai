from django.db.models import Max

from orders.models import Order, OrderStatusLog


def snapshot(user):
    """Panelni jonli yangilash uchun: oxirgi buyurtma id, yangilar soni va o'zgarish belgisi (token)."""
    orders = Order.objects.filter(shop__owner=user)
    last_id = orders.aggregate(m=Max("id"))["m"] or 0
    log_id = OrderStatusLog.objects.filter(order__shop__owner=user).aggregate(m=Max("id"))["m"] or 0
    new_count = orders.filter(status=Order.STATUS_NEW).count()
    return {"last_id": last_id, "new_count": new_count, "token": f"{last_id}:{log_id}:{new_count}"}


def panel(request):
    """Yon paneldagi "yangi buyurtmalar" belgisi va jonli yangilanish boshlang'ich holati."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    snap = snapshot(user)
    return {"new_orders_count": snap["new_count"], "live_after": snap["last_id"], "live_token": snap["token"]}
