import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from . import botconfig
from .crypto import decrypt, encrypt, token_hash


def _new_link_code() -> str:
    return secrets.token_urlsafe(9)


class Shop(models.Model):
    """Bitta do'kon = bitta Telegram bot + bitta katalog.

    MVP da har bir foydalanuvchi (egasi) bitta do'konga ega.
    """

    LANG_CHOICES = [("uz", "O'zbekcha"), ("ru", "Ruscha")]

    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop")
    name = models.CharField("Do'kon nomi", max_length=120)
    # Bot tokeni faqat shifrlangan holda saqlanadi. Ishlatish: shop.bot_token (o'qish/yozish).
    token_encrypted = models.TextField(blank=True, default="", editable=False)
    token_hash = models.CharField(max_length=64, blank=True, default="", editable=False)
    bot_username = models.CharField(max_length=64, blank=True, editable=False)
    owner_telegram_id = models.BigIntegerField(null=True, blank=True, editable=False)
    owner_link_code = models.CharField(max_length=32, default=_new_link_code, editable=False)
    default_language = models.CharField("Asosiy til", max_length=2, choices=LANG_CHOICES, default="uz")
    delivery_info = models.TextField(
        "Yetkazib berish va to'lov",
        blank=True,
        help_text="Masalan: Toshkent bo'ylab 1 kunda, 50 000 so'mdan yuqori buyurtmada bepul. To'lov naqd yoki Click.",
    )
    work_hours = models.CharField("Ish vaqti", max_length=120, blank=True)
    extra_instructions = models.TextField(
        "Botga qo'shimcha ko'rsatma",
        blank=True,
        help_text="Masalan: Chegirma bermang. Doim xushmuomala va qisqa javob bering.",
    )
    is_active = models.BooleanField("Bot yoqilgan", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Do'kon"
        verbose_name_plural = "Do'konlar"
        constraints = [
            models.UniqueConstraint(
                fields=["token_hash"], condition=~Q(token_hash=""), name="uniq_shop_token_hash"
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def bot_token(self) -> str:
        return decrypt(self.token_encrypted) if self.token_encrypted else ""

    @bot_token.setter
    def bot_token(self, value: str) -> None:
        value = (value or "").strip()
        self.token_encrypted = encrypt(value) if value else ""
        self.token_hash = token_hash(value) if value else ""

    @property
    def effective_token(self) -> str:
        """Ishlatiladigan token: panelniki, bo'lmasa .env (TELEGRAM_BOT_TOKEN) dagi."""
        return botconfig.effective_token(self)

    @property
    def token_source(self) -> str:
        return botconfig.token_source(self)

    @property
    def effective_owner_id(self):
        return botconfig.effective_owner_id(self)

    @property
    def has_token(self) -> bool:
        return bool(self.effective_token)

    @property
    def masked_token(self) -> str:
        """Tokenni interfeysda to'liq ko'rsatmaslik uchun."""
        token = self.effective_token
        if not token:
            return ""
        return f"{token[:5]}…{token[-4:]}" if len(token) > 12 else "••••"

    def regenerate_link_code(self) -> None:
        self.owner_link_code = _new_link_code()
        self.owner_telegram_id = None
        self.save(update_fields=["owner_link_code", "owner_telegram_id"])

    @classmethod
    def link_owner(cls, shop_id: int, code: str, telegram_id: int) -> bool:
        """Egasini Telegramga ulaydi. Kod bir martalik: ishlatilgach darhol almashtiriladi.

        Bitta UPDATE bilan bajariladi, shuning uchun bir vaqtda ikki marta ishlatib bo'lmaydi.
        """
        if not code:
            return False
        updated = cls.objects.filter(pk=shop_id, owner_link_code=code).update(
            owner_telegram_id=telegram_id, owner_link_code=_new_link_code()
        )
        return updated == 1


class AuditEvent(models.Model):
    """Xavfsizlik jurnali: kirish, parol, token va muhim amallar. Parol, token va boshqa sirlar HECH QACHON yozilmaydi."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=32)
    detail = models.CharField(max_length=200, blank=True)
    ip = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Xavfsizlik hodisasi"
        verbose_name_plural = "Xavfsizlik hodisalari"
