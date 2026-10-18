from django.db import models

from catalog.models import Product
from conversations.models import Customer
from shops.models import Shop


class Order(models.Model):
    STATUS_NEW = "new"
    STATUS_CONFIRMED = "confirmed"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_NEW, "Yangi"),
        (STATUS_CONFIRMED, "Qabul qilindi"),
        (STATUS_DELIVERED, "Yetkazildi"),
        (STATUS_CANCELLED, "Bekor qilindi"),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="orders")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    customer_name = models.CharField("Mijoz ismi", max_length=120)
    phone = models.CharField("Telefon", max_length=20)
    address = models.TextField("Manzil")
    total = models.DecimalField("Jami (so'm)", max_digits=14, decimal_places=0, default=0)
    status = models.CharField("Holati", max_length=12, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Buyurtma #{self.pk} — {self.customer_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    # Buyurtma vaqtidagi nom va narx (katalog keyin o'zgarsa ham buyurtma buzilmaydi)
    name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=12, decimal_places=0)
    quantity = models.PositiveIntegerField()

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self) -> str:
        return f"{self.name} × {self.quantity}"
