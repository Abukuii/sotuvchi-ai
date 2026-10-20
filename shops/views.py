from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.importer import ImportErrorBase, build_template_xlsx, import_catalog
from catalog.models import Product
from conversations.models import Conversation
from orders.models import Order

from . import analytics, notify, throttle
from .forms import CatalogUploadForm, ProductForm, ShopForm, SignupForm
from .models import Shop


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
            messages.success(request, "Xush kelibsiz! Avval bot tokenini ulang va katalogni yuklang.")
            return redirect("shop_settings")
    return render(request, "registration/signup.html", {"form": form})


@shop_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)  # joriy sessiya saqlanadi, boshqalari bekor bo'ladi
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
        "setup_done": bool(shop.has_token and products_count and shop.owner_telegram_id),
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
    qs = Order.objects.filter(shop=request.shop).prefetch_related("items")
    status = request.GET.get("status", "")
    if status in dict(Order.STATUS_CHOICES):
        qs = qs.filter(status=status)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/orders.html", {"page": page, "status": status, "statuses": Order.STATUS_CHOICES})


@shop_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk, shop=request.shop)
    return render(request, "panel/order_detail.html", {"order": order, "statuses": Order.STATUS_CHOICES})


@shop_required
@require_POST
def order_status(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "shop"), pk=pk, shop=request.shop)
    new_status = request.POST.get("status", "")
    if new_status not in dict(Order.STATUS_CHOICES):
        messages.error(request, "Noto'g'ri holat.")
        return redirect("order_detail", pk=order.pk)
    changed = new_status != order.status
    order.status = new_status
    order.save(update_fields=["status"])
    messages.success(request, "Buyurtma holati yangilandi.")
    if changed and request.POST.get("notify") == "on":
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
