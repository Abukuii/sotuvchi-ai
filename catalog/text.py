"""Matnni normallashtirish: o'zbek (lotin/kirill) va rus tillari uchun.

Maqsad: "Ko'ylak", "кўйлак" va "koylak" bir xil tokenga aylansin, shunda
mijoz qaysi alifboda yozmasin, qidiruv ishlaydi.
"""
import re

_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}
_APOSTROPHES = "'`’‘ʻʼ´"
_APOS_RE = re.compile(f"[{re.escape(_APOSTROPHES)}]")
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Qidiruvga xalaqit beradigan umumiy so'zlar (lotin alifbosiga o'girilgan holda)
STOPWORDS = {
    # o'zbekcha
    "narxi", "narx", "qancha", "necha", "pul", "bormi", "bor", "yoq", "kerak", "menga", "iltimos",
    "salom", "assalomu", "alaykum", "va", "bilan", "uchun", "haqida", "mavjud", "sotiladi",
    "olmoqchiman", "buyurtma", "bering", "beraman", "qanday", "qaysi", "nima", "bu", "shu",
    "som", "sum", "dona", "ta", "ni", "da", "ga", "dan",
    # ruscha
    "skolko", "stoit", "cena", "est", "li", "nujen", "nujna", "nujno", "pojalusta", "privet",
    "zdravstvuyte", "hochu", "xochu", "kupit", "zakaz", "i", "dlya", "pro", "kakoy", "kakaya",
    "chto", "eto", "u", "vas", "mne", "na", "v", "s", "po", "kak",
}


def normalize(text: str) -> str:
    """Kichik harf, kirill → lotin, apostrof va tinish belgilarini olib tashlash."""
    text = (text or "").lower()
    text = _APOS_RE.sub("", text)
    out = []
    for ch in text:
        out.append(_CYR_TO_LAT.get(ch, ch))
    return "".join(out)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize(text))


def keywords(text: str) -> list[str]:
    """Qidiruv uchun foydali tokenlar (stop-so'zlarsiz)."""
    return [t for t in tokenize(text) if t not in STOPWORDS and (len(t) >= 2 or t.isdigit())]


def detect_language(text: str, default: str = "uz") -> str:
    """Juda oddiy til aniqlash: 'uz' yoki 'ru'.

    - O'zbek kirill harflari (ў қ ғ ҳ) → uz
    - Kirill + ruscha harflar (ы э ё щ ъ) → ru
    - Kirill bo'lsa-yu aniq belgi bo'lmasa → ru (ko'proq ehtimol)
    - Lotin → ruscha so'zlar ro'yxatiga qarab, aks holda uz
    """
    low = (text or "").lower()
    if re.search(r"[ўқғҳ]", low):
        return "uz"
    if re.search(r"[а-яё]", low):
        return "ru"
    tokens = set(tokenize(low))
    ru_latin_markers = {"privet", "skolko", "stoit", "zdravstvuyte", "pojalusta", "spasibo", "hochu", "xochu"}
    if tokens & ru_latin_markers:
        return "ru"
    return default if default in {"uz", "ru"} else "uz"
