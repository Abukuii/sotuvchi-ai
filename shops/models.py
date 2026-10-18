import secrets

from django.conf import settings
from django.db import models


def _new_link_code() -> str:
    return secrets.token_urlsafe(9)


class Shop(models.Model):
    """Bitta do'kon = bitta Telegram bot + bitta katalog.

    MVP da har bir foydalanuvchi (egasi) bitta do'konga ega.
    """

    LANG_CHOICES = [("uz", "O'zbekcha"), ("ru", "Ruscha")]

    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop")
    name = models.CharField("Do'kon nomi", max_length=120)
    bot_token = models.CharField("Telegram bot tokeni", max_length=100, blank=True)
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

    def __str__(self) -> str:
        return self.name

    @property
    def masked_token(self) -> str:
        """Tokenni interfeysda to'liq ko'rsatmaslik uchun."""
        if not self.bot_token:
            return ""
        return f"{self.bot_token[:5]}…{self.bot_token[-4:]}" if len(self.bot_token) > 12 else "••••"

    def regenerate_link_code(self) -> None:
        self.owner_link_code = _new_link_code()
        self.owner_telegram_id = None
        self.save(update_fields=["owner_link_code", "owner_telegram_id"])
