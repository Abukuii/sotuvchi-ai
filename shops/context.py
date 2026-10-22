from orders.models import Order


def panel(request):
    """Yon paneldagi "yangi buyurtmalar" belgisi uchun."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"new_orders_count": Order.objects.filter(shop__owner=user, status=Order.STATUS_NEW).count()}
