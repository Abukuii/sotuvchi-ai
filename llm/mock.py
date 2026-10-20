"""Offline "mock" provayder: tashqi API siz demo va testlar uchun.

LLM emas, oddiy qoidalar: katalogdan topilgan mahsulotni aytadi, buyurtma
niyatini, telefon, ism va manzilni oddiy andozalar bilan ajratib oladi.
Real LLM bilan bir xil JSON formatida javob qaytaradi, shuning uchun butun
oqim (dvigatel, validatsiya, buyurtma yaratish) mock bilan ham tekshiriladi.
"""
import json
import re

from catalog.text import normalize, tokenize
from conversations.slots import extract_slots

from .base import LLMProvider, LLMRequest

ORDER_PREFIXES = ("buyurtma", "olaman", "olmoq", "zakaz", "beru", "xochu", "kupit", "sotib")
YES_TOKENS = {"ha", "xa", "da", "ok", "oke", "okey", "tasdiqlayman", "tasdiq", "podtverjdayu", "confirm", "yes"}

TEXTS = {
    "uz": {
        "found": "{name} — {price} so'm, omborda {stock} dona bor.",
        "out": "{name} — {price} so'm, afsuski hozir omborda yo'q.",
        "ask_more": "Buyurtma bermoqchi bo'lsangiz, ayting.",
        "need_name": "Buyurtma uchun ismingizni yozing.",
        "need_phone": "Telefon raqamingizni yozing.",
        "need_address": "Yetkazib berish manzilini yozing.",
        "unknown": "Bu haqda aniq ma'lumotim yo'q, savolingizni do'kon egasiga uzataman.",
        "hello": "Assalomu alaykum! Qaysi mahsulot qiziqtirmoqda?",
        "ok": "Rahmat!",
    },
    "ru": {
        "found": "{name} — {price} сум, в наличии {stock} шт.",
        "out": "{name} — {price} сум, сейчас нет в наличии.",
        "ask_more": "Если хотите оформить заказ, напишите.",
        "need_name": "Для заказа напишите ваше имя.",
        "need_phone": "Напишите ваш номер телефона.",
        "need_address": "Напишите адрес доставки.",
        "unknown": "Точной информации нет, передам ваш вопрос владельцу магазина.",
        "hello": "Здравствуйте! Какой товар вас интересует?",
        "ok": "Спасибо!",
    },
}

_PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{7,}\d)")


def _quantity(text: str) -> int:
    without_phone = _PHONE_RE.sub(" ", text)
    for m in re.finditer(r"\b(\d{1,2})\b", without_phone):
        value = int(m.group(1))
        if 1 <= value <= 99:
            return value
    return 1


class MockProvider(LLMProvider):
    name = "mock"

    def generate(self, request: LLMRequest) -> str:
        meta = request.meta
        lang = meta.get("language", "uz")
        t = TEXTS.get(lang, TEXTS["uz"])
        text = meta.get("last_user", "")
        hits = meta.get("hits", [])
        draft = dict(meta.get("draft") or {})
        items = list(draft.get("items") or [])
        tokens = tokenize(text)

        wants_order = any(tok.startswith(ORDER_PREFIXES) for tok in tokens)
        if wants_order and hits and not items:
            items = [{"product_id": hits[0]["id"], "quantity": _quantity(text)}]
        draft["items"] = items

        # Buyurtma boshlangan bo'lsa, ism/telefon/manzilni xabardan ajratib olamiz
        if items:
            draft.update(extract_slots(text, draft, allow_name=not meta.get("product_mentioned", False)))

        complete = bool(items and draft.get("customer_name") and draft.get("phone") and draft.get("address"))
        confirmed = complete and bool(set(tokens) & YES_TOKENS)

        if items:
            if not draft.get("customer_name"):
                reply, intent = t["need_name"], "order"
            elif not draft.get("phone"):
                reply, intent = t["need_phone"], "order"
            elif not draft.get("address"):
                reply, intent = t["need_address"], "order"
            else:
                reply, intent = t["ok"], "order"
        elif hits:
            top = hits[0]
            key = "found" if top["stock"] > 0 else "out"
            reply = t[key].format(name=top["name"], price=top["price"], stock=top["stock"]) + " " + t["ask_more"]
            intent = "question"
        elif tokens and not normalize(text).strip("0123456789 "):
            reply, intent = t["unknown"], "handoff"
        elif any(tok.startswith(("salom", "assalom", "privet", "zdravstv")) for tok in tokens):
            reply, intent = t["hello"], "smalltalk"
        else:
            reply, intent = t["unknown"], "handoff"

        return json.dumps(
            {"reply": reply, "intent": intent, "draft": draft, "confirmed": confirmed},
            ensure_ascii=False,
        )
