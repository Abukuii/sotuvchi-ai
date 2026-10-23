from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.sessions.models import Session
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.importer import ImportErrorBase, build_template_xlsx, import_catalog
from catalog.models import Product
from conversations.models import Conversation
from orders import services as order_services
from orders.models import Order

from . import analytics, audit, context, geo, notify, throttle
from .forms import CatalogUploadForm, ProductForm, ShopForm, SignupForm
from .models import AuditEvent, Shop


def shop_required(view):
    """Foydalanuvchi tizimga kirgan va do'koni bo'lishi shart. Hamma ma'lumot shu do'kon bilan cheklanadi."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        shop = Shop.objects.filter(owner=request.user).first()
        if shop is None:
            shop = Shop.objects.create(owner=request.user, name=f"{request.user.get_username()} do'koni")
        request.shop = shop
        return view(request, *args, **kwargs)

    return wrapper


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST or None)
    ip_key = f"signup-ip:{throttle.client_ip(request)}"
    if request.method == "POST":
        if throttle.count(ip_key) >= settings.SIGNUP_MAX_PER_HOUR:
            form.add_error(None, "Bu manzildan juda ko'p ro'yxatdan o'tish urinishi bo'ldi. Keyinroq urinib ko'ring.")
            return render(request, "registration/signup.html", {"form": form}, status=429)
        if form.is_valid():
            throttle.hit(ip_key, 3600)
            user = form.save()
            login(request, user)
            audit.record(request, "signup", user=user)
            messages.success(request, "Xush kelibsiz! Avval bot tokenini ulang va katalogni yuklang.")
            return redirect("shop_settings")
    return render(request, "registration/signup.html", {"form": form})


def landing(request):
    """Ochiq bosh sahifa: mahsulot haqida. Tizimga kirganlar uchun "Panelga o'tish" tugmasi ko'rsatiladi."""
    return render(request, "landing.html")


@shop_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        audit.record(request, "password_changed")  # joriy sessiya saqlanadi, boshqalari bekor bo'ladi
        messages.success(request, "Parol yangilandi.")
        return redirect("shop_settings")
    return render(request, "registration/password_change.html", {"form": form})


@shop_required
def dashboard(request):
    shop = request.shop
    products_count = Product.objects.filter(shop=shop, is_active=True).count()
    data = analytics.build_dashboard(shop, analytics.parse_days(request.GET.get("days")))
    context = {
        "shop": shop,
        "a": data,
        "products_count": products_count,
        "setup_done": bool(shop.has_token and products_count and shop.effective_owner_id),
        "recent_orders": Order.objects.filter(shop=shop).prefetch_related("items")[:5],
        "llm_provider": settings.LLM_PROVIDER,
        "owner_link": f"https://t.me/{shop.bot_username}?start={shop.owner_link_code}" if shop.bot_username else "",
    }
    return render(request, "panel/dashboard.html", context)


@shop_required
def shop_settings(request):
    shop = request.shop
    form = ShopForm(request.POST or None, instance=shop)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        new_token = form.cleaned_data.get("bot_token")
        token_changed = False
        if new_token and new_token != shop.bot_token:
            saved.bot_token = new_token
            token_changed = True
        elif form.cleaned_data.get("remove_token"):
            saved.bot_token = ""
            token_changed = True
        if token_changed:
            audit.record(request, "token_changed" if saved.bot_token else "token_removed")  # tokenning o'zi yozilmaydi
            saved.bot_username = ""  # bot qayta ishga tushganda yangilanadi
        saved.save()
        if token_changed:
            # Egasining Telegram ulanishi eski bot bilan bog'liq edi: yangi botda qayta ulash kerak
            saved.regenerate_link_code()
        messages.success(request, "Sozlamalar saqlandi. Bot o'zgarishlarni ~15 soniyada qabul qiladi.")
        return redirect("shop_settings")
    return render(request, "panel/settings.html", {"form": form, "shop": shop})


@shop_required
@require_POST
def regenerate_link(request):
    request.shop.regenerate_link_code()
    audit.record(request, "link_regenerated")
    messages.success(request, "Yangi ulash kodi yaratildi. Telegramni qayta ulang.")
    return redirect("dashboard")


@shop_required
def catalog(request):
    shop = request.shop
    qs = Product.objects.filter(shop=shop)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(category__icontains=q) | Q(sku__icontains=q))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "panel/catalog.html", {"page": page, "q": q, "upload_form": CatalogUploadForm()})


@shop_required
@require_POST
def catalog_upload(request):
    form = CatalogUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Fayl tanlanmadi.")
        return redirect("catalog")
    upload = form.cleaned_data["file"]
    if upload.size > settings.MAX_UPLOAD_BYTES:
        messages.error(request, f"Fayl juda katta (maksimum {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
        return redirect("catalog")
    try:
        result = import_catalog(request.shop, upload.name, upload.read())
    except ImportErrorBase as exc:
        messages.error(request, str(exc))
        return redirect("catalog")
    audit.record(request, "catalog_import", f"{result.created} yangi, {result.updated} yangilandi")
    messages.success(request, f"Yuklandi: {result.created} ta yangi, {result.updated} ta yangilandi, {result.skipped} ta o'tkazib yuborildi.")
    for err in result.errors[:10]:
        messages.warning(request, err)
    if len(result.errors) > 10:
        messages.warning(request, f"...va yana {len(result.errors) - 10} ta xato.")
    return redirect("catalog")


@shop_required
def catalog_template(request):
    response = HttpResponse(
        build_template_xlsx(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="katalog-shablon.xlsx"'
    return response


@shop_required
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk, shop=request.shop) if pk else None
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.shop = request.shop
        obj.save()
        messages.success(request, "Mahsulot saqlandi.")
        return redirect("catalog")
    return render(request, "panel/product_form.html", {"form": form, "product": product})


@shop_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, shop=request.shop)
    product.delete()
    messages.success(request, "Mahsulot o'chirildi.")
    return redirect("catalog")


@shop_required
def orders(request):
    base = Order.objects.filter(shop=request.shop)
    qs = base.prefetch_related("items")
    status = request.GET.get("status", "")
    if status in dict(Order.STATUS_CHOICES):
        qs = qs.filter(status=status)
    else:
        status = ""
    counts = {r["status"]: r["n"] for r in base.values("status").annotate(n=Count("id"))}
    tabs = [("", "Hammasi", sum(counts.values()))] + [(v, label, counts.get(v, 0)) for v, label in Order.STATUS_CHOICES]
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/orders.html", {"page": page, "status": status, "tabs": tabs})


@shop_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items", "status_log"), pk=pk, shop=request.shop)
    labels = dict(Order.STATUS_CHOICES)
    actions = [(value, ACTION_LABELS[value]) for value in order_services.allowed_next(order.status)]
    history = [(log, labels.get(log.from_status, log.from_status), labels.get(log.to_status, log.to_status)) for log in order.status_log.all()]
    flow = [(v, labels[v]) for v in order_services.FLOW]
    passed = order_services.FLOW[: order_services.FLOW.index(order.status)] if order.status in order_services.FLOW else []
    if order.status == Order.STATUS_CANCELLED:  # bekor qilingunga qadar bosib o'tilgan bosqichlar
        reached = {log.from_status for log in order.status_log.all()} & set(order_services.FLOW)
        passed = [v for v in order_services.FLOW if v in reached]
    ctx = {"order": order, "actions": actions, "history": history, "flow": flow, "passed": passed}
    if order.has_location:
        ctx["map_url"] = geo.map_url(order.latitude, order.longitude)
    return render(request, "panel/order_detail.html", ctx)


ACTION_LABELS = {
    Order.STATUS_CONFIRMED: "Qabul qilish",
    Order.STATUS_SHIPPED: "Yuborildi deb belgilash",
    Order.STATUS_DELIVERED: "Yetkazildi deb belgilash",
    Order.STATUS_CANCELLED: "Bekor qilish",
}


@shop_required
@require_POST
def order_status(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "shop"), pk=pk, shop=request.shop)
    new_status = request.POST.get("status", "")
    if new_status not in dict(Order.STATUS_CHOICES):
        messages.error(request, "Noto'g'ri holat.")
        return redirect("order_detail", pk=order.pk)
    try:
        changed = order_services.change_status(order, new_status, source="panel")
    except order_services.InvalidTransition:
        messages.error(request, "Bu holatga o'tkazib bo'lmaydi (yetkazilgan yoki bekor qilingan buyurtma o'zgarmaydi).")
        return redirect("order_detail", pk=order.pk)
    if not changed:
        messages.info(request, "Buyurtma allaqachon shu holatda.")
        return redirect("order_detail", pk=order.pk)
    audit.record(request, "order_status", f"#{order.pk} → {new_status}")
    messages.success(request, "Buyurtma holati yangilandi." + (" Mahsulot qoldig'i omborga qaytarildi." if new_status == Order.STATUS_CANCELLED else ""))
    if request.POST.get("notify") == "on":
        sent = notify.notify_customer_status(order, new_status)
        if sent is True:
            messages.success(request, "Mijozga Telegramda xabar yuborildi.")
        elif sent is False:
            messages.warning(request, "Holat saqlandi, lekin mijozga xabar yuborib bo'lmadi (bot tokenini va internetni tekshiring).")
    return redirect("order_detail", pk=order.pk)


@shop_required
def conversations(request):
    qs = Conversation.objects.filter(customer__shop=request.shop).select_related("customer")
    if request.GET.get("attention") == "1":
        qs = qs.filter(needs_attention=True)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/conversations.html", {"page": page, "attention": request.GET.get("attention") == "1"})


@shop_required
@require_POST
def conversation_delete(request, pk):
    """Mijoz ma'lumotlarini o'chirish (suhbat, xabarlar, mijoz yozuvi). Buyurtmalar saqlanadi."""
    conv = get_object_or_404(Conversation.objects.select_related("customer"), pk=pk, customer__shop=request.shop)
    conv.customer.delete()
    audit.record(request, "conversation_deleted")
    messages.success(request, "Suhbat va mijoz ma'lumotlari o'chirildi. Buyurtma yozuvlari saqlab qolindi.")
    return redirect("conversations")


@shop_required
def conversation_detail(request, pk):
    conv = get_object_or_404(Conversation.objects.select_related("customer"), pk=pk, customer__shop=request.shop)
    if request.method == "POST" and request.POST.get("resolve") == "1":
        conv.needs_attention = False
        conv.save(update_fields=["needs_attention"])
        messages.success(request, "Belgilandi: hal qilindi.")
        return redirect("conversation_detail", pk=conv.pk)
    return render(request, "panel/conversation_detail.html", {"conv": conv, "chat": conv.messages.all()})


@shop_required
def security(request):
    """Xavfsizlik sahifasi: so'nggi hodisalar, holat tekshiruvi va boshqa seanslardan chiqish."""
    events = list(AuditEvent.objects.filter(Q(user=request.user) | Q(user__isnull=True, username=request.user.get_username()))[:50])
    day_ago = timezone.now() - timedelta(days=1)
    failed = AuditEvent.objects.filter(
        username=request.user.get_username(), action__in=["login_failed", "login_blocked"], created_at__gte=day_ago
    ).count()
    checks = [
        ("Bot tokeni bazada shifrlangan holda saqlanadi", True),
        ("Sayt HTTPS orqali ochilgan", request.is_secure()),
        ("So'nggi 24 soatda muvaffaqiyatsiz kirish urinishlari yo'q", failed == 0),
    ]
    rows = [(e, audit.LABELS.get(e.action, e.action), e.action in audit.WARN) for e in events]
    return render(request, "panel/security.html", {"rows": rows, "checks": checks, "failed": failed})


@shop_required
@require_POST
def revoke_sessions(request):
    """Shu foydalanuvchining joriy seansdan boshqa barcha seanslarini tugatadi (yo'qolgan qurilma uchun)."""
    current = request.session.session_key
    removed = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.session_key != current and session.get_decoded().get("_auth_user_id") == str(request.user.pk):
            session.delete()
            removed += 1
    audit.record(request, "sessions_revoked", f"{removed} ta")
    messages.success(request, f"Boshqa seanslar tugatildi: {removed} ta.")
    return redirect("security")


@shop_required
def live_state(request):
    """Jonli yangilanish: brauzer har ~5 soniyada so'raydi. Yangi buyurtmalar va o'zgarish belgisini qaytaradi."""
    snap = context.snapshot(request.user)
    try:
        after = max(0, int(request.GET.get("after", "0")))
    except ValueError:
        after = 0
    fresh = []
    if after:
        for order in Order.objects.filter(shop=request.shop, pk__gt=after).order_by("pk")[:5]:
            fresh.append({"id": order.pk, "name": order.customer_name, "total": int(order.total), "url": reverse("order_detail", args=[order.pk])})
    return JsonResponse({"token": snap["token"], "last_id": snap["last_id"], "new": snap["new_count"], "fresh": fresh})
