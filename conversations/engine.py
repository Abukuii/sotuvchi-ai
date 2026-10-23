"""Suhbat dvigateli: mijoz xabari → LLM → tekshirilgan javob / buyurtma.

Xavfsizlik va ishonchlilik qoidalari:
- LLM narx, qoldiq va jami summani belgilamaydi: hammasi bazadan olinadi.
- LLM qaytargan product_id faqat shu do'konning faol mahsulotlariga tegishli bo'lishi kerak.
- Buyurtma faqat mijoz serverda ko'rsatilgan xulosani aniq tasdiqlagandan keyin yaratiladi.
- LLM ishlamasa, mijozga muloyim javob beriladi, egasiga xabar ketadi.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from catalog.search import Hit, search_products
from catalog.text import detect_language, tokenize
from llm import LLMError, LLMRequest, get_provider
from orders.models import Order, OrderItem

from shops import geo

from .models import Conversation, Customer, Message
from .prompts import build_system_prompt
from .slots import extract_slots

logger = logging.getLogger(__name__)

VALID_INTENTS = {"question", "order", "handoff", "smalltalk"}
CANCEL_TOKENS = ("bekor", "otmen", "cancel", "otkaz")
MAX_QTY = 999

STR = {
    "uz": {
        "already": "Buyurtmangiz allaqachon qabul qilingan. Yangi buyurtma uchun yozing.",
        "need_name": "Buyurtma uchun ismingizni yozing.",
        "need_phone": "Rahmat, {name}! Endi telefon raqamingizni yozing (masalan, +998901234567).",
        "need_address": "Yetkazib berish manzilini yozing yoki 📍 lokatsiyangizni yuboring.",
        "loc_no_cart": "Avval mahsulot tanlang: lokatsiya buyurtma manzili uchun kerak bo'ladi.",
        "loc_bad": "Lokatsiyani o'qib bo'lmadi. Manzilni matn bilan yozing.",
        "loc_saved": "📍 Lokatsiya qabul qilindi.",
        "loc_btn": "📍 Lokatsiyani yuborish",
        "loc_cancel": "Bekor qilish",
        "rate_limit": "Juda tez yozyapsiz. Bir daqiqadan keyin qayta urinib ko'ring.",
        "empty": "Savolingizni matn ko'rinishida yozing.",
        "llm_down": "Hozir javob bera olmayapman. Xabaringizni do'kon egasiga uzatdim, tez orada bog'lanishadi.",
        "handoff": "Savolingizni do'kon egasiga uzatdim, tez orada javob berishadi.",
        "summary_title": "Buyurtmangiz:",
        "total": "Jami",
        "name": "Ism",
        "phone": "Telefon",
        "address": "Manzil",
        "confirm_q": "Hammasi to'g'rimi? Tasdiqlash uchun \"Ha\" deb yozing. O'zgartirmoqchi bo'lsangiz, nimani o'zgartirishni ayting.",
        "order_done": "Buyurtmangiz qabul qilindi (№{id}). Tez orada siz bilan bog'lanamiz. Rahmat!",
        "bad_phone": "Telefon raqami noto'g'ri ko'rindi. Iltimos, +998901234567 ko'rinishida yozing.",
        "out_of_stock": "\"{name}\" hozir omborda yo'q.",
        "reduced": "\"{name}\" dan omborda faqat {stock} dona bor, shuncha miqdorni qo'shdim.",
        "stock_changed": "Afsuski, buyurtma tayyorlanayotganda \"{name}\" qoldig'i yetmay qoldi. Iltimos, miqdorni qayta tanlang.",
        "cancelled": "Buyurtma bekor qilindi. Yana nima kerak bo'lsa, yozing.",
        "currency": "so'm",
        "owner_new_order": "Yangi buyurtma №{id}",
        "owner_customer": "Mijoz",
        "owner_handoff": "Mijoz javob kutmoqda",
        "owner_llm_down": "Bot javob bera olmadi (AI xizmati xatosi). Mijozga yozing",
    },
    "ru": {
        "already": "Ваш заказ уже принят. Для нового заказа напишите.",
        "need_name": "Для заказа напишите ваше имя.",
        "need_phone": "Спасибо, {name}! Теперь напишите номер телефона (например, +998901234567).",
        "need_address": "Напишите адрес доставки или отправьте 📍 геолокацию.",
        "loc_no_cart": "Сначала выберите товар: геолокация нужна для адреса заказа.",
        "loc_bad": "Не удалось прочитать геолокацию. Напишите адрес текстом.",
        "loc_saved": "📍 Геолокация получена.",
        "loc_btn": "📍 Отправить геолокацию",
        "loc_cancel": "Отмена",
        "rate_limit": "Вы пишете слишком быстро. Попробуйте через минуту.",
        "empty": "Напишите ваш вопрос текстом.",
        "llm_down": "Сейчас не могу ответить. Я передал ваше сообщение владельцу магазина, он скоро свяжется с вами.",
        "handoff": "Передал ваш вопрос владельцу магазина, скоро ответят.",
        "summary_title": "Ваш заказ:",
        "total": "Итого",
        "name": "Имя",
        "phone": "Телефон",
        "address": "Адрес",
        "confirm_q": "Всё верно? Для подтверждения напишите «Да». Если нужно что-то изменить, напишите что именно.",
        "order_done": "Ваш заказ принят (№{id}). Скоро свяжемся с вами. Спасибо!",
        "bad_phone": "Номер телефона выглядит неверно. Напишите, пожалуйста, в формате +998901234567.",
        "out_of_stock": "«{name}» сейчас нет в наличии.",
        "reduced": "«{name}»: в наличии только {stock} шт., добавил столько.",
        "stock_changed": "К сожалению, пока оформлялся заказ, остаток «{name}» закончился. Выберите количество заново.",
        "cancelled": "Заказ отменён. Напишите, если что-то ещё нужно.",
        "currency": "сум",
        "owner_new_order": "Новый заказ №{id}",
        "owner_customer": "Клиент",
        "owner_handoff": "Клиент ждёт ответа",
        "owner_llm_down": "Бот не смог ответить (ошибка AI-сервиса). Напишите клиенту",
    },
}


def draft_version(draft: dict) -> str:
    """Qoralama holatining qisqa belgisi: eski \"Tasdiqlash\" tugmasi yangilangan buyurtmani tasdiqlab yubormasligi uchun."""
    import hashlib

    payload = json.dumps(
        {k: draft.get(k) for k in ("items", "customer_name", "phone", "address", "lat", "lon")},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()[:8]


class AlreadyProcessed(Exception):
    """Bu buyurtma boshqa so'rov tomonidan allaqachon yaratilgan (ikki marta "Ha" bosilganda)."""


_URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b(?:t\.me|telegram\.me|instagram\.com|bit\.ly|wa\.me)/\S+)", re.IGNORECASE)
MAX_REPLY_CHARS = 4000


def strip_unknown_urls(reply: str, allowed_text: str) -> str:
    """LLM javobidagi havolalardan faqat do'kon ma'lumotida bor bo'lganlarini qoldiradi.

    Mijoz "bu havolani yubor" deb LLM ni aldasa ham, bot begona havola tarqatmaydi.
    """
    allowed = allowed_text.lower()

    def keep_or_drop(match: re.Match) -> str:
        url = match.group(0).rstrip(".,;:!?)»\"'")
        return match.group(0) if url.lower() in allowed else ""

    return re.sub(r"[ \t]{2,}", " ", _URL_RE.sub(keep_or_drop, reply)).strip()


@dataclass
class BotReply:
    text: str
    owner_notice: str | None = None
    order_id: int | None = None
    awaiting_confirmation: bool = False  # tugmali "Tasdiqlash" ko'rsatish uchun
    draft_version: str = ""
    lang: str = "uz"
    ask_location: bool = False  # manzil so'ralganda "📍 Lokatsiya yuborish" tugmasini ko'rsatish


# ---------- yordamchi funksiyalar ----------

def money(value) -> str:
    return f"{int(value):,}".replace(",", " ")


def clean_text(value, limit: int = 200) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def normalize_phone(value) -> str | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 9:
        return "+998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    if 10 <= len(digits) <= 15:
        return "+" + digits
    return None


def parse_llm_json(raw: str) -> dict:
    """LLM javobini tekshirib, xavfsiz tuzilmaga aylantiradi. Xato bo'lsa ValueError."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("JSON topilmadi")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON obyekt emas")
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("reply bo'sh")
    intent = data.get("intent")
    draft = data.get("draft")
    return {
        "reply": reply.strip()[:1500],
        "intent": intent if intent in VALID_INTENTS else "question",
        "draft": draft if isinstance(draft, dict) else {},
        "confirmed": data.get("confirmed") is True,
    }


def sanitize_items(shop, raw_items, lang: str) -> tuple[list[dict], list[str]]:
    """LLM bergan mahsulot ro'yxatini bazaga qarab tekshiradi."""
    t = STR[lang]
    notes: list[str] = []
    if not isinstance(raw_items, list):
        return [], notes
    products = {p.pk: p for p in Product.objects.filter(shop=shop, is_active=True)}
    merged: dict[int, int] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("product_id"))
            qty = int(item.get("quantity", 1))
        except (TypeError, ValueError):
            continue
        if pid not in products or qty < 1:
            continue
        merged[pid] = min(merged.get(pid, 0) + qty, MAX_QTY)
    items: list[dict] = []
    for pid, qty in merged.items():
        product = products[pid]
        if product.stock <= 0:
            notes.append(t["out_of_stock"].format(name=product.name))
            continue
        if qty > product.stock:
            notes.append(t["reduced"].format(name=product.name, stock=product.stock))
            qty = product.stock
        items.append({"product_id": pid, "quantity": qty})
    return items, notes


def build_summary(shop, draft: dict, lang: str) -> tuple[str, Decimal]:
    t = STR[lang]
    products = {p.pk: p for p in Product.objects.filter(shop=shop, pk__in=[i["product_id"] for i in draft["items"]])}
    total = Decimal(0)
    lines = [t["summary_title"]]
    for item in draft["items"]:
        product = products[item["product_id"]]
        subtotal = product.price * item["quantity"]
        total += subtotal
        lines.append(f"• {product.name} × {item['quantity']} = {money(subtotal)} {t['currency']}")
    lines.append(f"{t['total']}: {money(total)} {t['currency']}")
    lines.append(f"{t['name']}: {draft['customer_name']}")
    lines.append(f"{t['phone']}: {draft['phone']}")
    lines.append(f"{t['address']}: {draft['address']}")
    lines.append("")
    lines.append(t["confirm_q"])
    return "\n".join(lines), total


def _customer_label(customer: Customer) -> str:
    label = customer.full_name or str(customer.telegram_id)
    if customer.username:
        label += f" (@{customer.username})"
    return label


def create_order(shop, customer: Customer, draft: dict, lang: str, conversation: Conversation) -> Order:
    """Buyurtmani yaratadi va qoldiqni kamaytiradi.

    Qoldiq yetmasa ValueError(mahsulot nomi), tasdiq allaqachon ishlatilgan bo'lsa AlreadyProcessed.
    Suhbat qatori qulflanadi, shuning uchun bir vaqtda kelgan ikkita "Ha" bitta buyurtma beradi.
    """
    with transaction.atomic():
        locked_conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if not locked_conv.awaiting_confirmation:
            raise AlreadyProcessed()
        locked_conv.awaiting_confirmation = False
        locked_conv.draft = {}
        locked_conv.save(update_fields=["awaiting_confirmation", "draft"])
        ids = [i["product_id"] for i in draft["items"]]
        locked = {p.pk: p for p in Product.objects.select_for_update().filter(shop=shop, pk__in=ids, is_active=True)}
        total = Decimal(0)
        for item in draft["items"]:
            product = locked.get(item["product_id"])
            if product is None:
                raise ValueError("mahsulot")
            if product.stock < item["quantity"]:
                raise ValueError(product.name)
        order = Order.objects.create(
            shop=shop,
            customer=customer,
            customer_name=draft["customer_name"],
            phone=draft["phone"],
            address=draft["address"],
            latitude=draft.get("lat") if geo.valid_coords(draft.get("lat"), draft.get("lon")) else None,
            longitude=draft.get("lon") if geo.valid_coords(draft.get("lat"), draft.get("lon")) else None,
        )
        for item in draft["items"]:
            product = locked[item["product_id"]]
            OrderItem.objects.create(
                order=order,
                product=product,
                name=product.name,
                unit_price=product.price,
                quantity=item["quantity"],
            )
            product.stock -= item["quantity"]
            product.save(update_fields=["stock", "updated_at"])
            total += product.price * item["quantity"]
        order.total = total
        order.save(update_fields=["total"])
    return order


def order_owner_notice(shop, order: Order, customer: Customer) -> str:
    t = STR[shop.default_language if shop.default_language in STR else "uz"]
    lines = [f"🆕 {t['owner_new_order'].format(id=order.pk)}"]
    lines.append(f"{t['owner_customer']}: {order.customer_name} ({_customer_label(customer)})")
    lines.append(f"{t['phone']}: {order.phone}")
    lines.append(f"{t['address']}: {order.address}")
    if order.has_location:
        lines.append(f"🗺 {geo.google_map_url(order.latitude, order.longitude)}")
    for item in order.items.all():
        lines.append(f"• {item.name} × {item.quantity} = {money(item.subtotal)} {t['currency']}")
    lines.append(f"{t['total']}: {money(order.total)} {t['currency']}")
    return "\n".join(lines)


def _history(conversation: Conversation) -> list[dict]:
    recent = list(conversation.messages.order_by("-created_at", "-id")[: settings.CHAT_HISTORY_LIMIT])
    recent.reverse()
    messages = [{"role": m.role, "content": m.text} for m in recent]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def _context_hits(shop, conversation: Conversation, text: str, draft: dict) -> list[Hit]:
    """Joriy xabar bo'yicha qidiradi; topilmasa, oldingi mijoz xabarlariga qaraydi.

    "2 ta olaman" kabi xabarda mahsulot nomi bo'lmaydi, lekin u oldingi savolga tegishli.
    Buyurtma qoralamasidagi mahsulotlar ham kontekstga qo'shiladi.
    """
    hits = search_products(shop, text, limit=5)
    if not hits:
        earlier = conversation.messages.filter(role=Message.ROLE_USER).order_by("-created_at", "-id")[1:4]
        for message in earlier:
            hits = search_products(shop, message.text, limit=5)
            if hits:
                break
    known = {h.product.pk for h in hits}
    wanted = [i.get("product_id") for i in draft.get("items", []) if isinstance(i, dict)]
    for product in Product.objects.filter(shop=shop, is_active=True, pk__in=[w for w in wanted if w not in known]):
        hits.append(Hit(product=product, score=0.0))
    return hits


def _ask_llm(provider, request: LLMRequest) -> dict:
    for _ in range(2):
        raw = provider.generate(request)  # LLMError yuqoriga uzatiladi
        try:
            return parse_llm_json(raw)
        except ValueError as exc:
            logger.warning("LLM noto'g'ri JSON qaytardi: %s", exc)
    raise LLMError("LLM kutilgan formatda javob bermadi")


def _save_reply(conversation: Conversation, text: str) -> None:
    Message.objects.create(conversation=conversation, role=Message.ROLE_ASSISTANT, text=text)
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=timezone.now())


# ---------- asosiy kirish nuqtasi ----------

def handle_location(shop, telegram_id: int, username: str, full_name: str, lat, lon) -> BotReply:
    """Mijoz lokatsiya yubordi: manzilga aylantirib qoralamaga yozadi va keyingi qadamni ko'rsatadi.

    Savat/qoralama (menyu yoki AI orqali) bo'lmasa, hech narsa saqlanmaydi.
    """
    customer, _ = Customer.objects.get_or_create(
        shop=shop,
        telegram_id=telegram_id,
        defaults={"username": (username or "")[:64], "full_name": (full_name or "")[:200], "language": shop.default_language},
    )
    lang = customer.language if customer.language in STR else "uz"
    t = STR[lang]
    if not geo.valid_coords(lat, lon):
        return BotReply(text=t["loc_bad"], lang=lang)
    lat, lon = round(float(lat), 6), round(float(lon), 6)
    conversation, _ = Conversation.objects.get_or_create(customer=customer)
    if not (conversation.draft or {}).get("items"):
        return BotReply(text=t["loc_no_cart"], lang=lang)
    window_start = timezone.now() - timedelta(minutes=1)
    if conversation.messages.filter(role=Message.ROLE_USER, created_at__gte=window_start).count() >= settings.RATE_LIMIT_PER_MINUTE:
        return BotReply(text=t["rate_limit"], lang=lang)
    address = geo.address_from_location(lat, lon, lang)  # tarmoq chaqiruvi: qulf va tranzaksiyadan tashqarida
    Message.objects.create(conversation=conversation, role=Message.ROLE_USER, text=f"[Lokatsiya] {geo.coords_text(lat, lon)}")
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        draft = dict(conversation.draft or {})
        if not draft.get("items"):  # kutish paytida bekor qilingan
            return BotReply(text=t["loc_no_cart"], lang=lang)
        draft.update({"address": address, "lat": lat, "lon": lon})
        complete = bool(draft.get("customer_name") and draft.get("phone"))
        conversation.draft = draft
        conversation.awaiting_confirmation = complete
        conversation.save(update_fields=["draft", "awaiting_confirmation"])
    if not draft.get("customer_name"):
        text = f"{t['loc_saved']}\n{t['need_name']}"
    elif not draft.get("phone"):
        text = f"{t['loc_saved']}\n{t['need_phone'].format(name=draft['customer_name'].split()[0])}"
    else:
        summary, _total = build_summary(shop, draft, lang)
        text = f"{t['loc_saved']}\n\n{summary}"
    _save_reply(conversation, text)
    return BotReply(
        text=text[:MAX_REPLY_CHARS],
        awaiting_confirmation=complete,
        draft_version=draft_version(draft) if complete else "",
        lang=lang,
    )


def handle_message(shop, telegram_id: int, username: str, full_name: str, text: str, provider=None) -> BotReply:
    text = (text or "").strip()[: settings.MAX_MESSAGE_CHARS]

    customer, _ = Customer.objects.get_or_create(
        shop=shop,
        telegram_id=telegram_id,
        defaults={"username": (username or "")[:64], "full_name": (full_name or "")[:200], "language": shop.default_language},
    )
    changed = False
    if (username or "")[:64] != customer.username:
        customer.username, changed = (username or "")[:64], True
    if (full_name or "")[:200] != customer.full_name:
        customer.full_name, changed = (full_name or "")[:200], True
    lang = detect_language(text, default=customer.language) if text else customer.language
    if lang != customer.language:
        customer.language, changed = lang, True
    if changed:
        customer.save()
    lang = customer.language if customer.language in STR else "uz"
    t = STR[lang]

    conversation, _ = Conversation.objects.get_or_create(customer=customer)

    if not text:
        return BotReply(text=t["empty"])

    # Spamdan himoya
    window_start = timezone.now() - timedelta(minutes=1)
    recent_count = conversation.messages.filter(role=Message.ROLE_USER, created_at__gte=window_start).count()
    if recent_count >= settings.RATE_LIMIT_PER_MINUTE:
        return BotReply(text=t["rate_limit"])

    Message.objects.create(conversation=conversation, role=Message.ROLE_USER, text=text)
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=timezone.now())

    # Bekor qilish: LLM ga bormasdan
    if any(tok.startswith(CANCEL_TOKENS) for tok in tokenize(text)) and conversation.draft:
        conversation.draft = {}
        conversation.awaiting_confirmation = False
        conversation.save(update_fields=["draft", "awaiting_confirmation"])
        _save_reply(conversation, t["cancelled"])
        return BotReply(text=t["cancelled"])

    provider = provider or get_provider()
    prev_draft = conversation.draft or {}
    hits = _context_hits(shop, conversation, text, prev_draft)
    catalog = list(Product.objects.filter(shop=shop, is_active=True).order_by("category", "name")[:200])
    system = build_system_prompt(shop, lang, hits, catalog, prev_draft)
    request = LLMRequest(
        system=system,
        messages=_history(conversation),
        meta={
            "language": lang,
            "last_user": text,
            "hits": [
                {"id": h.product.pk, "name": h.product.name, "price": int(h.product.price), "stock": h.product.stock}
                for h in hits
            ],
            "draft": prev_draft,
            "product_mentioned": bool(search_products(shop, text, limit=1)),
        },
    )

    try:
        parsed = _ask_llm(provider, request)
    except LLMError as exc:
        logger.error("LLM xatosi (shop=%s): %s", shop.pk, exc)
        Conversation.objects.filter(pk=conversation.pk).update(needs_attention=True)
        owner_t = STR[shop.default_language if shop.default_language in STR else "uz"]
        notice = f"⚠️ {owner_t['owner_llm_down']}: {_customer_label(customer)}\n“{text[:300]}”"
        _save_reply(conversation, t["llm_down"])
        return BotReply(text=t["llm_down"], owner_notice=notice)

    allowed_text = " ".join(
        [shop.delivery_info, shop.work_hours, shop.extra_instructions] + [p.description for p in catalog]
    )
    parsed["reply"] = strip_unknown_urls(parsed["reply"], allowed_text) or t["handoff"]

    llm_draft = parsed["draft"]

    # 1) mahsulotlar
    raw_items = llm_draft["items"] if isinstance(llm_draft.get("items"), list) else prev_draft.get("items", [])
    if not raw_items and prev_draft.get("items"):
        raw_items = prev_draft["items"]
    items, notes = sanitize_items(shop, raw_items, lang)

    # 2) mijoz ma'lumotlari
    name = clean_text(llm_draft.get("customer_name"), 120) or prev_draft.get("customer_name", "")
    address = clean_text(llm_draft.get("address"), 300) or prev_draft.get("address", "")
    phone = prev_draft.get("phone", "")
    raw_phone = llm_draft.get("phone")
    bad_phone = False
    if raw_phone:
        normalized = normalize_phone(raw_phone)
        if normalized:
            phone = normalized
        else:
            bad_phone = True

    # Zaxira: LLM maydonni to'ldirmagan bo'lsa (masalan, yalang'och "Otabek" javobi), aniq qoidalar bilan to'ldiramiz
    filled_by_rules = False
    if items:
        product_mentioned = bool(search_products(shop, text, limit=1))
        extra = extract_slots(
            text,
            {"customer_name": name, "phone": phone, "address": address},
            allow_name=not product_mentioned,
        )
        if not name and extra.get("customer_name"):
            name, filled_by_rules = clean_text(extra["customer_name"], 120), True
        if not phone and extra.get("phone"):
            normalized = normalize_phone(extra["phone"])
            if normalized:
                phone, filled_by_rules = normalized, True
            else:
                bad_phone = True
        if not address and extra.get("address"):
            address, filled_by_rules = clean_text(extra["address"], 300), True

    new_draft = {"items": items, "customer_name": name, "phone": phone, "address": address}
    if address == prev_draft.get("address", "") and geo.valid_coords(prev_draft.get("lat"), prev_draft.get("lon")):
        new_draft["lat"], new_draft["lon"] = prev_draft["lat"], prev_draft["lon"]  # manzil o'zgarsa, eski koordinata tashlanadi
    state_changed = new_draft != {
        "items": prev_draft.get("items", []),
        "customer_name": prev_draft.get("customer_name", ""),
        "phone": prev_draft.get("phone", ""),
        "address": prev_draft.get("address", ""),
        **({"lat": prev_draft["lat"], "lon": prev_draft["lon"]} if "lat" in prev_draft else {}),
    }
    was_awaiting = conversation.awaiting_confirmation
    complete = bool(items and name and phone and address)

    reply_text = parsed["reply"]
    owner_notice = None
    order_id = None
    awaiting = False
    needs_attention = False

    is_handoff = parsed["intent"] == "handoff"

    if complete and parsed["confirmed"] and was_awaiting and not state_changed:
        try:
            order = create_order(shop, customer, new_draft, lang, conversation)
        except AlreadyProcessed:
            reply_text = t["already"]
            new_draft = {}
            is_handoff = False
        except ValueError as exc:
            reply_text = t["stock_changed"].format(name=str(exc))
            new_draft["items"] = []
        else:
            reply_text = t["order_done"].format(id=order.pk)
            owner_notice = order_owner_notice(shop, order, customer)
            order_id = order.pk
            new_draft = {}
            is_handoff = False
    elif complete:
        summary, _total = build_summary(shop, new_draft, lang)
        if was_awaiting and not state_changed and not parsed["confirmed"] and parsed["intent"] in {"question", "handoff", "smalltalk"}:
            # Mijoz tasdiqlash paytida boshqa savol berdi: javobni saqlab, xulosani qayta ko'rsatamiz
            reply_text = f"{reply_text}\n\n{summary}"
        else:
            reply_text = summary
        awaiting = True
    else:
        if bad_phone:
            reply_text = t["bad_phone"]
        elif filled_by_rules and items:
            # LLM javobi eskirgan bo'lishi mumkin (masalan, ismni yana so'raydi): keyingi bo'sh maydonni biz so'raymiz
            if not name:
                reply_text = t["need_name"]
            elif not phone:
                reply_text = t["need_phone"].format(name=name.split()[0])
            else:
                reply_text = t["need_address"]
        if notes:
            reply_text = " ".join(notes) + "\n" + reply_text

    if is_handoff:
        needs_attention = True
        owner_t = STR[shop.default_language if shop.default_language in STR else "uz"]
        owner_notice = f"💬 {owner_t['owner_handoff']}: {_customer_label(customer)}\n“{text[:300]}”"

    reply_text = reply_text[:MAX_REPLY_CHARS]

    conversation.draft = new_draft
    conversation.awaiting_confirmation = awaiting
    if needs_attention:
        conversation.needs_attention = True
    conversation.save(update_fields=["draft", "awaiting_confirmation", "needs_attention"])
    _save_reply(conversation, reply_text)
    return BotReply(
        text=reply_text,
        owner_notice=owner_notice,
        order_id=order_id,
        awaiting_confirmation=awaiting,
        draft_version=draft_version(new_draft) if awaiting else "",
        lang=lang,
        ask_location=bool(items and name and phone and not address and not order_id),
    )
