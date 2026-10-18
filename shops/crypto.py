"""Bot tokenlarini bazada shifrlab saqlash (Fernet: AES-128-CBC + HMAC).

Kalit TOKEN_ENCRYPTION_KEY dan (yoki SECRET_KEY dan) hosil qilinadi.
Baza oqib ketsa ham, tokenlar kalitsiz o'qilmaydi.
"""
import base64
import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


def _key_material() -> bytes:
    return (settings.TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY).encode()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"fernet:" + _key_material()).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Shifrni ochadi. Kalit noto'g'ri bo'lsa bo'sh qator qaytaradi (token qayta kiritilishi kerak)."""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        logger.error("Bot tokenini shifrdan ochib bo'lmadi: kalit o'zgargan bo'lishi mumkin.")
        return ""


def token_hash(value: str) -> str:
    """Tokenning bir martalik (qaytarilmas) belgisi: takrorlanishni tekshirish uchun."""
    return hmac.new(_key_material(), b"hash:" + value.encode(), hashlib.sha256).hexdigest()
