"""Xavfsizlik jurnali (AuditEvent) va kirish hodisalari uchun signallar.

Jurnal xatosi hech qachon asosiy amalni buzmasligi kerak, shuning uchun hamma xato yutiladi (faqat log).
"""
import logging
from datetime import timedelta

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from . import throttle
from .models import AuditEvent

logger = logging.getLogger(__name__)

RETENTION_DAYS = 180

LABELS = {
    "login": "Tizimga kirish",
    "login_failed": "Kirish muvaffaqiyatsiz",
    "login_blocked": "Kirish vaqtincha bloklandi",
    "logout": "Chiqish",
    "signup": "Ro'yxatdan o'tish",
    "password_changed": "Parol o'zgartirildi",
    "sessions_revoked": "Boshqa seanslardan chiqarildi",
    "token_changed": "Bot tokeni o'zgartirildi",
    "token_removed": "Bot tokeni o'chirildi",
    "link_regenerated": "Telegram ulash kodi yangilandi",
    "catalog_import": "Katalog yuklandi",
    "order_status": "Buyurtma holati o'zgartirildi",
    "conversation_deleted": "Mijoz ma'lumotlari o'chirildi",
}
WARN = {"login_failed", "login_blocked"}


def record(request, action: str, detail: str = "", user=None, username: str = "") -> None:
    try:
        user = user or getattr(request, "user", None)
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        AuditEvent.objects.create(
            user=user,
            username=(username or (user.get_username() if user else ""))[:150],
            action=action,
            detail=detail[:200],
            ip=throttle.client_ip(request) if request is not None else "",
        )
        if action == "login":  # eski yozuvlarni tozalash (kirishda bir marta, arzon)
            AuditEvent.objects.filter(created_at__lt=timezone.now() - timedelta(days=RETENTION_DAYS)).delete()
    except Exception:  # noqa: BLE001
        logger.exception("Xavfsizlik jurnaliga yozib bo'lmadi")


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    record(request, "login", user=user)


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user is not None:
        record(request, "logout", user=user)


@receiver(user_login_failed)
def _on_failed(sender, credentials, request=None, **kwargs):
    # Faqat login nomi yoziladi (parol hech qachon); mavjud bo'lmagan nomlar ham yoziladi — hujumni ko'rish uchun.
    record(request, "login_failed", username=str(credentials.get("username", ""))[:150])
