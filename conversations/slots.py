"""Buyurtma ma'lumotlarini (ism, telefon, manzil) matndan aniq qoidalar bilan ajratib olish.

Nega kerak: LLM ba'zan "Otabek" kabi yalang'och javobni ism deb draftga yozmaydi va bot
bir savolni takrorlab qolardi. Bu modul LLM ga qo'shimcha zaxira: LLM bergan qiymat har doim
ustun, bu yerdagi qoidalar faqat bo'sh qolgan maydonlarni to'ldiradi.
"""
import re

from catalog.text import STOPWORDS, tokenize

PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{7,}\d)")
# "tel: 90 111 22 33" kabi yozuvlarda "tel" so'zi manzilga qo'shilib ketmasin
_PHONE_WITH_LABEL_RE = re.compile(
    r"(?:\b(?:tel|telefon|telefonim|raqam|raqamim|nomer|тел|телефон|номер)\b[.:]?\s*)?(\+?\d[\d\s\-()]{7,}\d)",
    re.IGNORECASE,
)
_NAME_PREFIX_RE = re.compile(
    r"^\s*(?:mening\s+)?(?:ismim|ismi|ism|familiyam|men|мен|меня зовут|мое имя|моё имя|имя)\s*[:\-]?\s+", re.IGNORECASE
)
_ADDR_PREFIX_RE = re.compile(r"^\s*(?:manzilim|manzil|adresim|adres|адрес)\s*[:\-]?\s*", re.IGNORECASE)
_NAME_WORD_RE = re.compile(r"^[^\W\d_]+(?:['’ʻ`\-.][^\W\d_]+)*\.?$", re.UNICODE)
_SPLIT_RE = re.compile(r"[,;\n]")

# Ism bo'lishi mumkin bo'lmagan so'zlar (javoblar, niyatlar, rahmat va h.k.), lotinga o'girilgan holda
NOT_NAME = {
    "ha", "xa", "yoq", "yok", "da", "net", "ok", "oke", "okey", "yes", "no", "bekor", "otmen", "cancel",
    "rahmat", "raxmat", "spasibo", "salom", "assalomu", "alaykum", "privet", "zdravstvuyte", "hop", "mayli",
    "olaman", "olmoqchiman", "buyurtma", "zakaz", "xochu", "hochu", "kerak", "tasdiqlayman", "tasdiq",
    "podtverjdayu", "manzil", "adres", "telefon", "nomer", "raqam", "ism", "imya", "narx", "price",
}


def looks_like_name(chunk: str) -> bool:
    words = chunk.split()
    if not 1 <= len(words) <= 4:
        return False
    if any(len(w) < 2 or len(w) > 30 or not _NAME_WORD_RE.match(w) for w in words):
        return False
    tokens = tokenize(chunk)
    if not tokens or any(t in NOT_NAME or t in STOPWORDS for t in tokens):
        return False
    return True


def _capitalize(name: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in name.split())[:120]


def extract_slots(text: str, current: dict, allow_name: bool = True) -> dict:
    """Matndan hali bo'sh maydonlarni topadi. Qaytadi: {"customer_name"?, "phone"?, "address"?}.

    allow_name=False: xabar katalogdagi mahsulotga tegishli bo'lsa, uni ism deb o'ylamaslik uchun.
    """
    updates: dict = {}
    text = (text or "").strip()
    if not text:
        return updates

    phone_match = PHONE_RE.search(text)
    if phone_match and not current.get("phone"):
        updates["phone"] = re.sub(r"[^\d+]", "", phone_match.group(1))

    rest = _PHONE_WITH_LABEL_RE.sub(" ", text).strip()

    name = current.get("customer_name") or ""
    address_text = ""
    addr_match = _ADDR_PREFIX_RE.match(rest)
    if addr_match:
        address_text = rest[addr_match.end():].strip()
        chunks: list[str] = []
    else:
        chunks = [c.strip() for c in _SPLIT_RE.split(rest) if c.strip()]
        # "ismim Ali, manzil: ..." kabi aralash xabar
        for idx, chunk in enumerate(chunks):
            m = _ADDR_PREFIX_RE.match(chunk)
            if m:
                address_text = ", ".join([chunk[m.end():].strip()] + chunks[idx + 1:]).strip(", ")
                chunks = chunks[:idx]
                break

    if not name and allow_name and chunks:
        first = _NAME_PREFIX_RE.sub("", chunks[0]).strip()
        if first and looks_like_name(first):
            name = _capitalize(first)
            updates["customer_name"] = name
            chunks = chunks[1:]

    if not current.get("address"):
        phone_known = bool(current.get("phone") or updates.get("phone"))
        if address_text:
            candidate = address_text
        elif name and phone_known and chunks:
            candidate = ", ".join(chunks)
        else:
            candidate = ""
        if len(candidate) >= 6 and "?" not in candidate and not looks_like_name(candidate):
            updates["address"] = candidate[:300]
    return updates
