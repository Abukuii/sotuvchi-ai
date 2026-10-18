from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from shops.models import Shop


class Product(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    sku = models.CharField("Kod", max_length=64, blank=True)
    name = models.CharField("Nomi", max_length=200)
    category = models.CharField("Toifa", max_length=120, blank=True)
    description = models.TextField("Tavsif", blank=True)
    price = models.DecimalField("Narxi (so'm)", max_digits=12, decimal_places=0, validators=[MinValueValidator(Decimal("0"))])
    stock = models.PositiveIntegerField("Qoldiq", default=0)
    is_active = models.BooleanField("Faol", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"
        ordering = ["category", "name"]
        indexes = [models.Index(fields=["shop", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.price} so'm)"

    @property
    def in_stock(self) -> bool:
        return self.stock > 0
