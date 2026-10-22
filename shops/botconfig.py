"""Bot tokeni va egasi sozlamalari: panel (shifrlangan, bazada) yoki .env (TELEGRAM_BOT_TOKEN).

Qoidalar:
* Panelda kiritilgan token har doim ustun turadi.
* .env dagi token bitta do'konga beriladi (bitta bot — bitta jarayon: ikki do'kon bir tokenni tinglasa
  Telegram "Conflict" xatosini beradi). Do'kon: TELEGRAM_BOT_SHOP_ID, bo'sh bo'lsa — tokeni yo'q eng birinchi faol do'kon.
* Boshqa do'kon shu tokenni panelda saqlagan bo'lsa, .env tokeni ishlatilmaydi.
* Token formati tekshiriladi; noto'g'ri bo'lsa e'tiborga olinmaydi (qiymat logga yozilmaydi).
"""
import logging
import re

from django.conf import settings

from .crypto import token_hash

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")
_warned: set[str] = set()


def env_token() -> str:
    token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    if token and not TOKEN_RE.match(token):
        if "bad" not in _warned:
            _warned.add("bad")
            logger.error("TELEGRAM_BOT_TOKEN formati noto'g'ri (raqam:harflar). .env ni tekshiring; e'tiborga olinmadi.")
        return ""
    return token


def env_shop_id() -> int | None:
    """.env tokeni qaysi do'konga tegishli (yoki None)."""
    token = env_token()
    if not token:
        return None
    from .models import Shop

    if Shop.objects.filter(token_hash=token_hash(token)).exists():
        return None  # shu token panelda saqlangan: panel ustun
    wanted = getattr(settings, "TELEGRAM_BOT_SHOP_ID", None)
    qs = Shop.objects.filter(is_active=True, token_encrypted="")
    if wanted:
        qs = qs.filter(pk=wanted)
    return qs.order_by("pk").values_list("pk", flat=True).first()


def effective_token(shop) -> str:
    own = shop.bot_token
    if own:
        return own
    return env_token() if env_shop_id() == shop.pk else ""


def token_source(shop) -> str:
    """"panel" | "env" | "" """
    if shop.token_encrypted:
        return "panel"
    return "env" if effective_token(shop) else ""


def effective_owner_id(shop):
    if shop.owner_telegram_id:
        return shop.owner_telegram_id
    owner = getattr(settings, "TELEGRAM_OWNER_ID", None)
    return owner if owner and env_shop_id() == shop.pk else None
