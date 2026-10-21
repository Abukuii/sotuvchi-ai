"""Telegram botning tugmali menyusi: katalog, savat, buyurtmalar, ma'lumot, sozlamalar.

Bu modul Telegramdan mustaqil: har bir amal `Screen` (matn + tugmalar ro'yxati) qaytaradi,
runner uni aiogram klaviaturasiga aylantiradi. Shuning uchun hammasi oddiy Django testlari bilan sinaladi.

Xavfsizlik va to'g'rilik qoidalari:
- Narx, qoldiq va mahsulot faqat bazadan olinadi, callback ma'lumotlariga ishonilmaydi (hammasi qayta tekshiriladi).
- Buyurtma faqat "Tasdiqlash" bosilganda, qoralama versiyasi mos kelsagina yaratiladi.
- Mijoz faqat o'z savati, buyurtmalari va ma'lumotlari bilan ishlaydi.
"""
from dataclasses import dataclass, field
from html import escape

from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from conversations.engine import (
    MAX_QTY,
    STR,
    AlreadyProcessed,
    _customer_label,
    _save_reply,
    build_summary,
    create_order,
    draft_version,
    money,
    order_owner_notice,
)
from conversations.models import Conversation, Customer, Message
from orders.models import Order

MAX_CART_LINES = 15
PAGE_SIZE = 6
CAT_PAGE_SIZE = 8
OTHER_CAT = {"uz": "Boshqa", "ru": "Прочее"}
LANGS = ("uz", "ru")

MENU = {
    "uz": {
        "catalog": "🛍 Katalog",
        "cart": "🛒 Savat",
        "orders": "📦 Buyurtmalarim",
        "info": "ℹ️ Ma'lumot",
        "settings": "⚙️ Sozlamalar",
    },
    "ru": {
        "catalog": "🛍 Каталог",
        "cart": "🛒 Корзина",
        "orders": "📦 Мои заказы",
        "info": "ℹ️ Информация",
        "settings": "⚙️ Настройки",
    },
}
MENU_LAYOUT = [["catalog", "cart"], ["orders", "info"], ["settings"]]
LABEL_TO_KEY = {label: key for lang in MENU.values() for key, label in lang.items()}

T = {
    "uz": {
        "home": "Bo'limni tanlang yoki savolingizni yozing, yordam beraman.",
        "cat_title": "🛍 <b>Toifani tanlang</b>",
        "prod_title": "🛍 <b>{cat}</b>\nMahsulotni tanlang",
        "no_products": "Hozircha katalog bo'sh.",
        "back": "⬅️ Orqaga",
        "prev": "◀️",
        "next": "▶️",
        "home_btn": "🏠 Menyu",
        "price": "Narxi",
        "in_stock": "Omborda bor",
        "few_left": "Oz qoldi: {n} dona",
        "sold_out": "Hozir omborda yo'q",
        "add": "🛒 Savatga ({qty})",
        "cart_btn": "🛒 Savat",
        "cart_full": "Savatda {n} tadan ortiq xil mahsulot bo'lmaydi",
        "added": "Savatga qo'shildi",
        "sold_out_toast": "Bu mahsulot hozir omborda yo'q",
        "reduced_toast": "Omborda faqat {n} dona bor",
        "gone": "Bu mahsulot endi mavjud emas.",
        "cart_empty": "Savatingiz bo'sh. Katalogdan mahsulot tanlang.",
        "cart_title": "🛒 <b>Savatingiz</b>",
        "checkout": "✅ Buyurtma berish",
        "clear": "🗑 Tozalash",
        "to_catalog": "🛍 Katalogga",
        "confirm": "✅ Tasdiqlash",
        "cancel": "❌ Bekor qilish",
        "cancelled_toast": "Bekor qilindi",
        "stale": "Buyurtma ma'lumoti o'zgargan. Yangi holatni tekshirib, qayta tasdiqlang.",
        "nothing_to_confirm": "Tasdiqlanadigan buyurtma yo'q.",
        "orders_title": "📦 <b>So'nggi buyurtmalaringiz</b>",
        "orders_empty": "Hali buyurtma bermagansiz.",
        "info_title": "ℹ️ <b>{shop}</b>",
        "work_hours": "Ish vaqti",
        "delivery": "Yetkazib berish",
        "not_set": "do'kon egasi hali kiritmagan",
        "operator": "👤 Operator bilan bog'lanish",
        "operator_sent": "Savolingiz do'kon egasiga yuborildi. Tez orada javob berishadi.",
        "settings_title": "⚙️ <b>Sozlamalar</b>",
        "language": "Til",
        "lang_set": "Til o'zgartirildi",
        "delete_data": "🗑 Ma'lumotlarimni o'chirish",
        "delete_ask": "Suhbat tarixi va shaxsiy ma'lumotlaringiz o'chiriladi (buyurtma yozuvlari do'konda qoladi). Davom etasizmi?",
        "delete_yes": "Ha, o'chirish",
        "deleted": "Ma'lumotlaringiz o'chirildi. Qayta yozsangiz, yangidan boshlaymiz.",
        "prefilled": "Oxirgi buyurtmangizdagi ma'lumotlar ishlatildi. Noto'g'ri bo'lsa, yangisini yozing.",
        "status": {"new": "Yangi", "confirmed": "Qabul qilindi", "delivered": "Yetkazildi", "cancelled": "Bekor qilindi"},
    },
    "ru": {
        "home": "Выберите раздел или напишите вопрос, я помогу.",
        "cat_title": "🛍 <b>Выберите категорию</b>",
        "prod_title": "🛍 <b>{cat}</b>\nВыберите товар",
        "no_products": "Каталог пока пуст.",
        "back": "⬅️ Назад",
        "prev": "◀️",
        "next": "▶️",
        "home_btn": "🏠 Меню",
        "price": "Цена",
        "in_stock": "В наличии",
        "few_left": "Осталось мало: {n} шт.",
        "sold_out": "Сейчас нет в наличии",
        "add": "🛒 В корзину ({qty})",
        "cart_btn": "🛒 Корзина",
        "cart_full": "В корзине не может быть больше {n} разных товаров",
        "added": "Добавлено в корзину",
        "sold_out_toast": "Этого товара сейчас нет в наличии",
        "reduced_toast": "В наличии только {n} шт.",
        "gone": "Этого товара больше нет.",
        "cart_empty": "Корзина пуста. Выберите товар в каталоге.",
        "cart_title": "🛒 <b>Ваша корзина</b>",
        "checkout": "✅ Оформить заказ",
        "clear": "🗑 Очистить",
        "to_catalog": "🛍 В каталог",
        "confirm": "✅ Подтвердить",
        "cancel": "❌ Отменить",
        "cancelled_toast": "Отменено",
        "stale": "Данные заказа изменились. Проверьте новое состояние и подтвердите снова.",
        "nothing_to_confirm": "Нет заказа для подтверждения.",
        "orders_title": "📦 <b>Ваши последние заказы</b>",
        "orders_empty": "Вы ещё не делали заказов.",
        "info_title": "ℹ️ <b>{shop}</b>",
        "work_hours": "Часы работы",
        "delivery": "Доставка",
        "not_set": "владелец пока не указал",
        "operator": "👤 Связаться с оператором",
        "operator_sent": "Ваш вопрос передан владельцу магазина. Скоро ответят.",
        "settings_title": "⚙️ <b>Настройки</b>",
        "language": "Язык",
        "lang_set": "Язык изменён",
        "delete_data": "🗑 Удалить мои данные",
        "delete_ask": "История переписки и личные данные будут удалены (записи о заказах останутся в магазине). Продолжить?",
        "delete_yes": "Да, удалить",
        "deleted": "Ваши данные удалены. Напишите снова, и мы начнём заново.",
        "prefilled": "Использованы данные из прошлого заказа. Если неверно, напишите новые.",
        "status": {"new": "Новый", "confirmed": "Принят", "delivered": "Доставлен", "cancelled": "Отменён"},
    },
}


def esc(value) -> str:
    """Telegram HTML rejimi uchun: foydalanuvchi/do'kon matni hech qachon teg sifatida talqin qilinmaydi."""
    return escape(str(value), quote=False)


@dataclass
class Screen:
    """text: Telegram HTML (parse_mode=HTML). Dinamik qiymatlar esc() orqali kiritiladi."""

    text: str
    rows: list[list[tuple[str, str]]] = field(default_factory=list)  # [(yozuv, callback_data)]
    toast: str = ""  # callback.answer() uchun qisqa xabar
    owner_notice: str | None = None
    show_menu: bool = False  # pastki doimiy menyuni ham yuborish
    replace: bool = True  # True: eski xabarni tahrirlash, False: yangi xabar
    deleted: bool = False
    followup_menu: str = ""  # bo'sh bo'lmasa: shu matn bilan pastki menyu alohida xabar sifatida yuboriladi


@dataclass
class Ctx:
    shop: object
    customer: Customer
    conv: Conversation
    lang: str

    @property
    def t(self):
        return T[self.lang]

    @property
    def s(self):
        return STR[self.lang]


def get_ctx(shop, telegram_id: int, username: str = "", full_name: str = "") -> Ctx:
    customer, _ = Customer.objects.get_or_create(
        shop=shop,
        telegram_id=telegram_id,
        defaults={"username": (username or "")[:64], "full_name": (full_name or "")[:200], "language": shop.default_language},
    )
    conv, _ = Conversation.objects.get_or_create(customer=customer)
    lang = customer.language if customer.language in T else "uz"
    return Ctx(shop, customer, conv, lang)


def menu_labels(lang: str) -> list[list[str]]:
    labels = MENU[lang if lang in MENU else "uz"]
    return [[labels[k] for k in row] for row in MENU_LAYOUT]


# ---------- yordamchi ----------

def _categories(shop, lang) -> list[str]:
    """Faol mahsulotlar toifalari (tartiblangan). Toifasizlar oxirida "Boshqa" sifatida."""
    names = sorted({c for c in Product.objects.filter(shop=shop, is_active=True).values_list("category", flat=True) if c})
    if Product.objects.filter(shop=shop, is_active=True, category="").exists():
        names.append("")
    return names


def _cat_title(cat: str, lang: str) -> str:
    return cat or OTHER_CAT[lang]


def _short(text: str, limit: int = 34) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _cart_items(ctx: Ctx):
    """Savat qatorlari: [(Product, qty)]. Mavjud bo'lmagan mahsulotlar savatdan tushib qoladi."""
    draft = ctx.conv.draft or {}
    wanted = {i["product_id"]: i["quantity"] for i in draft.get("items", []) if isinstance(i, dict)}
    products = {p.pk: p for p in Product.objects.filter(shop=ctx.shop, is_active=True, pk__in=wanted)}
    return [(products[pid], qty) for pid, qty in wanted.items() if pid in products]


def _save_cart(ctx: Ctx, pairs) -> None:
    """Savatni qoralamaga yozadi. Savat o'zgarsa, tasdiq kutish holati bekor bo'ladi."""
    draft = dict(ctx.conv.draft or {})
    draft["items"] = [{"product_id": p.pk, "quantity": q} for p, q in pairs if q > 0]
    ctx.conv.draft = draft if draft["items"] else {}  # savat bo'shasa, qoralama ham tozalanadi
    ctx.conv.awaiting_confirmation = False
    ctx.conv.save(update_fields=["draft", "awaiting_confirmation"])


def _home_row(ctx: Ctx):
    return [(ctx.t["home_btn"], "m:home")]


# ---------- ekranlar ----------

def screen_home(ctx: Ctx) -> Screen:
    return Screen(ctx.t["home"], show_menu=True, replace=False)


def screen_categories(ctx: Ctx, page: int = 0) -> Screen:
    t = ctx.t
    cats = _categories(ctx.shop, ctx.lang)
    if not cats:
        return Screen(t["no_products"], [_home_row(ctx)])
    if len(cats) == 1:  # bitta toifa bo'lsa, to'g'ridan-to'g'ri mahsulotlar
        return screen_products(ctx, 0, 0)
    pages = max(1, -(-len(cats) // CAT_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = []
    for idx in range(page * CAT_PAGE_SIZE, min(len(cats), (page + 1) * CAT_PAGE_SIZE)):
        count = Product.objects.filter(shop=ctx.shop, is_active=True, category=cats[idx]).count()
        rows.append([(f"{_short(_cat_title(cats[idx], ctx.lang))} ({count})", f"m:ls:{idx}:0")])
    nav = []
    if page > 0:
        nav.append((t["prev"], f"m:cat:{page - 1}"))
    if page < pages - 1:
        nav.append((t["next"], f"m:cat:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(_home_row(ctx))
    return Screen(t["cat_title"], rows)


def screen_products(ctx: Ctx, cat_idx: int, page: int) -> Screen:
    t = ctx.t
    cats = _categories(ctx.shop, ctx.lang)
    if not 0 <= cat_idx < len(cats):
        return screen_categories(ctx, 0)
    qs = list(Product.objects.filter(shop=ctx.shop, is_active=True, category=cats[cat_idx]).order_by("name", "pk"))
    pages = max(1, -(-len(qs) // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = []
    for p in qs[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
        mark = "" if p.stock > 0 else "✖ "
        rows.append([(f"{mark}{_short(p.name)} — {money(p.price)}", f"m:it:{p.pk}:{cat_idx}:{page}")])
    nav = []
    if page > 0:
        nav.append((t["prev"], f"m:ls:{cat_idx}:{page - 1}"))
    if page < pages - 1:
        nav.append((t["next"], f"m:ls:{cat_idx}:{page + 1}"))
    if nav:
        rows.append(nav)
    back = [(t["back"], "m:cat:0")] if len(cats) > 1 else []
    rows.append(back + _home_row(ctx))
    title = t["prod_title"].format(cat=esc(_cat_title(cats[cat_idx], ctx.lang)))
    if pages > 1:
        title += f" ({page + 1}/{pages})"
    return Screen(title, rows)


def _stock_text(ctx: Ctx, product: Product) -> str:
    if product.stock <= 0:
        return ctx.t["sold_out"]
    if product.stock <= 5:
        return ctx.t["few_left"].format(n=product.stock)
    return ctx.t["in_stock"]


def screen_product(ctx: Ctx, pid: int, cat_idx: int, page: int, qty: int = 1) -> Screen:
    t = ctx.t
    product = Product.objects.filter(shop=ctx.shop, is_active=True, pk=pid).first()
    if product is None:
        return Screen(t["gone"], [[(t["to_catalog"], "m:cat:0")]], toast=t["gone"])
    lines = [f"<b>{esc(product.name)}</b>"]
    if product.category:
        lines.append(f"<i>{esc(product.category)}</i>")
    lines.append("")
    lines.append(f"💰 {t['price']}: <b>{money(product.price)}</b> {ctx.s['currency']}")
    icon = "⛔" if product.stock <= 0 else ("⚠️" if product.stock <= 5 else "✅")
    lines.append(f"{icon} {_stock_text(ctx, product)}")
    if product.description:
        lines += ["", esc(product.description[:600])]
    rows = []
    if product.stock > 0:
        qty = max(1, min(qty, product.stock, MAX_QTY))
        rows.append(
            [
                ("➖", f"m:q:{pid}:{max(1, qty - 1)}:{cat_idx}:{page}"),
                (str(qty), f"m:q:{pid}:{qty}:{cat_idx}:{page}"),
                ("➕", f"m:q:{pid}:{min(qty + 1, product.stock, MAX_QTY)}:{cat_idx}:{page}"),
            ]
        )
        rows.append([(t["add"].format(qty=qty), f"m:add:{pid}:{qty}:{cat_idx}:{page}")])
    rows.append([(t["back"], f"m:ls:{cat_idx}:{page}")] + _home_row(ctx))
    return Screen("\n".join(lines), rows)


def screen_cart(ctx: Ctx, toast: str = "") -> Screen:
    t = ctx.t
    pairs = _cart_items(ctx)
    if not pairs:
        return Screen(t["cart_empty"], [[(t["to_catalog"], "m:cat:0")]], toast=toast)
    lines = [t["cart_title"]]
    rows = []
    total = 0
    for product, qty in pairs:
        subtotal = product.price * qty
        total += subtotal
        lines.append(f"▫️ {esc(product.name)} × {qty} — <b>{money(subtotal)}</b> {ctx.s['currency']}")
        rows.append(
            [
                ("➖", f"m:cq:{product.pk}:-1"),
                (f"{_short(product.name, 18)} ×{qty}", f"m:cq:{product.pk}:0"),
                ("➕", f"m:cq:{product.pk}:1"),
                ("🗑", f"m:cd:{product.pk}"),
            ]
        )
    lines.append("")
    lines.append(f"💳 <b>{ctx.s['total']}: {money(total)} {ctx.s['currency']}</b>")
    rows.append([(t["checkout"], "m:co")])
    rows.append([(t["clear"], "m:cc"), (t["to_catalog"], "m:cat:0")])
    return Screen("\n".join(lines), rows, toast=toast)


def confirm_rows(ctx: Ctx, version: str):
    return [[(ctx.t["confirm"], f"m:ok:{version}"), (ctx.t["cancel"], "m:no")]]


def screen_orders(ctx: Ctx) -> Screen:
    t = ctx.t
    orders = list(Order.objects.filter(shop=ctx.shop, customer=ctx.customer).order_by("-created_at", "-pk")[:5])
    if not orders:
        return Screen(t["orders_empty"], [_home_row(ctx)])
    icons = {"new": "🆕", "confirmed": "✅", "delivered": "🚚", "cancelled": "✖️"}
    lines = [t["orders_title"], ""]
    for o in orders:
        when = timezone.localtime(o.created_at).strftime("%d.%m")
        status = t["status"].get(o.status, o.status)
        lines.append(f"{icons.get(o.status, '•')} <b>№{o.pk}</b> · {when} · {money(o.total)} {ctx.s['currency']} · <i>{esc(status)}</i>")
    return Screen("\n".join(lines), [_home_row(ctx)])


def screen_info(ctx: Ctx) -> Screen:
    t = ctx.t
    shop = ctx.shop
    lines = [
        t["info_title"].format(shop=esc(shop.name)),
        "",
        f"🕘 {t['work_hours']}: {esc(shop.work_hours or t['not_set'])}",
        f"🚚 {t['delivery']}: {esc(shop.delivery_info or t['not_set'])}",
    ]
    return Screen("\n".join(lines), [[(t["operator"], "m:op")], _home_row(ctx)])


def screen_settings(ctx: Ctx) -> Screen:
    t = ctx.t
    lang_row = [(("✓ " if code == ctx.lang else "") + name, f"m:lang:{code}") for code, name in (("uz", "O'zbekcha"), ("ru", "Русский"))]
    text = f"{t['settings_title']}\n\n🌐 {t['language']}: <b>{'Oʻzbekcha' if ctx.lang == 'uz' else 'Русский'}</b>"
    return Screen(text, [lang_row, [(t["delete_data"], "m:del")], _home_row(ctx)])


# ---------- amallar ----------

def cart_add(ctx: Ctx, pid: int, qty: int) -> tuple[bool, str]:
    t = ctx.t
    with transaction.atomic():
        ctx.conv = Conversation.objects.select_for_update().get(pk=ctx.conv.pk)
        product = Product.objects.filter(shop=ctx.shop, is_active=True, pk=pid).first()
        if product is None:
            return False, t["gone"]
        if product.stock <= 0:
            return False, t["sold_out_toast"]
        pairs = dict((p.pk, [p, q]) for p, q in _cart_items(ctx))
        if pid not in pairs and len(pairs) >= MAX_CART_LINES:
            return False, t["cart_full"].format(n=MAX_CART_LINES)
        current = pairs[pid][1] if pid in pairs else 0
        wanted = max(1, min(current + qty, MAX_QTY))
        toast = t["added"]
        if wanted > product.stock:
            wanted = product.stock
            toast = t["reduced_toast"].format(n=product.stock)
        pairs[pid] = [product, wanted]
        _save_cart(ctx, [(p, q) for p, q in pairs.values()])
    return True, toast


def cart_change(ctx: Ctx, pid: int, delta: int) -> str:
    t = ctx.t
    with transaction.atomic():
        ctx.conv = Conversation.objects.select_for_update().get(pk=ctx.conv.pk)
        pairs = _cart_items(ctx)
        out, toast = [], ""
        for product, qty in pairs:
            if product.pk == pid:
                new = qty + delta
                if new > product.stock:
                    new, toast = product.stock, t["reduced_toast"].format(n=product.stock)
                qty = max(0, min(new, MAX_QTY))
            out.append((product, qty))
        _save_cart(ctx, out)
    return toast


def cart_remove(ctx: Ctx, pid: int) -> None:
    with transaction.atomic():
        ctx.conv = Conversation.objects.select_for_update().get(pk=ctx.conv.pk)
        _save_cart(ctx, [(p, q) for p, q in _cart_items(ctx) if p.pk != pid])


def cart_clear(ctx: Ctx) -> None:
    Conversation.objects.filter(pk=ctx.conv.pk).update(draft={}, awaiting_confirmation=False)
    ctx.conv.refresh_from_db()


def _prefill_from_last_order(ctx: Ctx) -> bool:
    draft = dict(ctx.conv.draft or {})
    if draft.get("customer_name") and draft.get("phone") and draft.get("address"):
        return False
    last = Order.objects.filter(shop=ctx.shop, customer=ctx.customer).order_by("-created_at", "-pk").first()
    if last is None:
        return False
    changed = False
    for key, value in (("customer_name", last.customer_name), ("phone", last.phone), ("address", last.address)):
        if not draft.get(key) and value:
            draft[key], changed = value, True
    if changed:
        ctx.conv.draft = draft
        ctx.conv.save(update_fields=["draft"])
    return changed


def checkout(ctx: Ctx) -> Screen:
    """Savatdan buyurtmaga o'tish: yetishmayotgan ma'lumotni so'raydi yoki xulosani ko'rsatadi."""
    t, s = ctx.t, ctx.s
    pairs = _cart_items(ctx)
    if not pairs:
        return screen_cart(ctx)
    prefilled = _prefill_from_last_order(ctx)
    draft = ctx.conv.draft or {}
    draft["items"] = [{"product_id": p.pk, "quantity": q} for p, q in pairs]
    name, phone, address = draft.get("customer_name", ""), draft.get("phone", ""), draft.get("address", "")
    cancel_row = [[(t["cancel"], "m:no")]]
    if not name:
        return Screen(esc(s["need_name"]), cancel_row, replace=False)
    if not phone:
        return Screen(esc(s["need_phone"].format(name=name.split()[0])), cancel_row, replace=False)
    if not address:
        return Screen(esc(s["need_address"]), cancel_row, replace=False)
    summary, _ = build_summary(ctx.shop, draft, ctx.lang)
    ctx.conv.draft = draft
    ctx.conv.awaiting_confirmation = True
    ctx.conv.save(update_fields=["draft", "awaiting_confirmation"])
    text = f"{esc(t['prefilled'])}\n\n{esc(summary)}" if prefilled else esc(summary)
    return Screen(text, confirm_rows(ctx, draft_version(draft)), replace=False)


def confirm(ctx: Ctx, version: str) -> Screen:
    t, s = ctx.t, ctx.s
    ctx.conv.refresh_from_db()
    draft = ctx.conv.draft or {}
    if not ctx.conv.awaiting_confirmation or not draft.get("items"):
        # Allaqachon tasdiqlangan (ikki marta bosish) yoki bekor qilingan
        return Screen(t["nothing_to_confirm"], toast=t["nothing_to_confirm"], replace=False)
    if draft_version(draft) != version:
        # Eski tugma: yangi holatni ko'rsatamiz, mijoz uni o'zi tasdiqlasin
        summary, _ = build_summary(ctx.shop, draft, ctx.lang)
        return Screen(f"{esc(t['stale'])}\n\n{esc(summary)}", confirm_rows(ctx, draft_version(draft)), replace=False)
    try:
        order = create_order(ctx.shop, ctx.customer, draft, ctx.lang, ctx.conv)
    except AlreadyProcessed:
        return Screen(esc(s["already"]), toast=s["already"], replace=False)
    except ValueError as exc:
        # Qoldiq yetmadi: tasdiq bekor, mijoz miqdorni qayta tanlaydi
        Conversation.objects.filter(pk=ctx.conv.pk).update(awaiting_confirmation=False)
        return Screen(esc(s["stock_changed"].format(name=str(exc))), [[(t["cart_btn"], "m:cart")]], replace=False)
    notice = order_owner_notice(ctx.shop, order, ctx.customer)
    text = s["order_done"].format(id=order.pk)
    _save_reply(ctx.conv, text)
    return Screen(f"🎉 <b>{esc(text)}</b>", [], owner_notice=notice, show_menu=True, replace=False)


def _complete(draft: dict) -> bool:
    return bool(draft.get("items") and draft.get("customer_name") and draft.get("phone") and draft.get("address"))


def cancel_draft(ctx: Ctx) -> Screen:
    cart_clear(ctx)
    return Screen(esc(ctx.s["cancelled"]), [[(ctx.t["to_catalog"], "m:cat:0")]], toast=ctx.t["cancelled_toast"])


def operator(ctx: Ctx) -> Screen:
    Conversation.objects.filter(pk=ctx.conv.pk).update(needs_attention=True)
    owner_t = STR[ctx.shop.default_language if ctx.shop.default_language in STR else "uz"]
    notice = f"💬 {owner_t['owner_handoff']}: {_customer_label(ctx.customer)}"
    Message.objects.create(conversation=ctx.conv, role=Message.ROLE_USER, text="[Operator so'raldi]")
    return Screen(ctx.t["operator_sent"], [_home_row(ctx)], owner_notice=notice, replace=False)


def set_language(ctx: Ctx, code: str) -> Screen:
    if code in LANGS:
        Customer.objects.filter(pk=ctx.customer.pk).update(language=code)
        ctx.customer.language, ctx.lang = code, code
    scr = screen_settings(ctx)
    scr.toast = ctx.t["lang_set"]
    scr.followup_menu = ctx.t["home"]  # pastki menyu yangi tilda qayta chiziladi
    return scr


def ask_delete(ctx: Ctx) -> Screen:
    return Screen(ctx.t["delete_ask"], [[(ctx.t["delete_yes"], "m:delyes"), (ctx.t["cancel"], "m:set")]])


def delete_data(ctx: Ctx) -> Screen:
    text = ctx.t["deleted"]
    ctx.customer.delete()  # suhbat va xabarlar o'chadi, buyurtmalar saqlanadi (SET_NULL)
    return Screen(text, [], deleted=True, replace=False)


# ---------- kirish nuqtalari ----------

def handle_menu_text(shop, telegram_id, username, full_name, text: str) -> Screen | None:
    """Pastki menyu tugmasi bosilgan bo'lsa ekran, aks holda None (oddiy matn → AI)."""
    text = (text or "").strip()
    key = next((k for label, k in LABEL_TO_KEY.items() if text == label), None)
    if key is None:
        return None
    ctx = get_ctx(shop, telegram_id, username, full_name)
    screen = {
        "catalog": lambda: screen_categories(ctx),
        "cart": lambda: screen_cart(ctx),
        "orders": lambda: screen_orders(ctx),
        "info": lambda: screen_info(ctx),
        "settings": lambda: screen_settings(ctx),
    }[key]()
    screen.replace = False
    return screen


def handle_command(shop, telegram_id, username, full_name, command: str) -> Screen | None:
    ctx = get_ctx(shop, telegram_id, username, full_name)
    mapping = {
        "menu": lambda: screen_home(ctx),
        "catalog": lambda: screen_categories(ctx),
        "cart": lambda: screen_cart(ctx),
        "orders": lambda: screen_orders(ctx),
        "info": lambda: screen_info(ctx),
        "settings": lambda: screen_settings(ctx),
        "help": lambda: screen_home(ctx),
    }
    make = mapping.get(command)
    if make is None:
        return None
    screen = make()
    screen.replace = False
    return screen


def _ints(parts, count):
    try:
        values = [int(x) for x in parts[:count]]
    except ValueError:
        return None
    return values if len(values) == count else None


def handle_callback(shop, telegram_id, username, full_name, data: str) -> Screen:
    """Inline tugma bosilganda: data = "m:<amal>:<argumentlar>". Noto'g'ri ma'lumot menyuga qaytaradi."""
    ctx = get_ctx(shop, telegram_id, username, full_name)
    parts = (data or "").split(":")
    if len(parts) < 2 or parts[0] != "m" or len(data) > 64:
        return screen_home(ctx)
    action, args = parts[1], parts[2:]
    try:
        if action == "home":
            return screen_home(ctx)
        if action == "cat":
            v = _ints(args, 1) or [0]
            return screen_categories(ctx, v[0])
        if action == "ls":
            v = _ints(args, 2)
            return screen_products(ctx, *v) if v else screen_categories(ctx)
        if action == "it":
            v = _ints(args, 3)
            return screen_product(ctx, *v) if v else screen_categories(ctx)
        if action == "q":
            v = _ints(args, 4)
            return screen_product(ctx, v[0], v[2], v[3], qty=v[1]) if v else screen_categories(ctx)
        if action == "add":
            v = _ints(args, 4)
            if not v:
                return screen_categories(ctx)
            ok, toast = cart_add(ctx, v[0], v[1])
            scr = screen_product(ctx, v[0], v[2], v[3], qty=1)
            scr.toast = toast
            return scr
        if action == "cart":
            return screen_cart(ctx)
        if action == "cq":
            v = _ints(args, 2)
            toast = cart_change(ctx, v[0], v[1]) if v else ""
            return screen_cart(ctx, toast=toast)
        if action == "cd":
            v = _ints(args, 1)
            if v:
                cart_remove(ctx, v[0])
            return screen_cart(ctx)
        if action == "cc":
            cart_clear(ctx)
            return screen_cart(ctx)
        if action == "co":
            return checkout(ctx)
        if action == "ok":
            return confirm(ctx, args[0] if args else "")
        if action == "no":
            return cancel_draft(ctx)
        if action == "ord":
            return screen_orders(ctx)
        if action == "info":
            return screen_info(ctx)
        if action == "op":
            return operator(ctx)
        if action == "set":
            return screen_settings(ctx)
        if action == "lang":
            return set_language(ctx, args[0] if args else "")
        if action == "del":
            return ask_delete(ctx)
        if action == "delyes":
            return delete_data(ctx)
    except IndexError:
        pass
    return screen_home(ctx)
