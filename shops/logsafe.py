"""Loglarda sirlarni yashirish.

Nega kerak: httpx har so'rovni INFO darajasida URL bilan yozadi, Telegram URL esa tokenni o'z ichiga oladi
(https://api.telegram.org/bot<TOKEN>/...). Shuningdek, istisno matnlarida kalitlar chiqib ketishi mumkin.
RedactingFormatter yakuniy matnni (istisno izi bilan) tozalaydi.
"""
import logging
import re

from django.conf import settings

MASK = "[yashirilgan]"
PATTERNS = [
    re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,50}"),  # Telegram bot tokeni
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),  # Google/Gemini kaliti
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),  # Groq kaliti
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{12,}"),  # Authorization sarlavhasi
    re.compile(r"(?i)\b(x-goog-api-key|api[_-]?key|token|secret|password)(\s*[=:]\s*)[^\s,;&'\"]{6,}"),
]


def _exact_secrets() -> list[str]:
    names = ("SECRET_KEY", "TOKEN_ENCRYPTION_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN")
    return [v for v in (getattr(settings, n, "") for n in names) if isinstance(v, str) and len(v) >= 8]


def redact(text: str) -> str:
    for secret in _exact_secrets():
        text = text.replace(secret, MASK)
    text = PATTERNS[0].sub(MASK, text)
    text = PATTERNS[1].sub(MASK, text)
    text = PATTERNS[2].sub(MASK, text)
    text = PATTERNS[3].sub(lambda m: f"{m.group(1)} {MASK}", text)
    text = PATTERNS[4].sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
