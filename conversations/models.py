from django.db import models

from shops.models import Shop


class Customer(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="customers")
    telegram_id = models.BigIntegerField()
    username = models.CharField(max_length=64, blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    language = models.CharField(max_length=2, default="uz")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mijoz"
        verbose_name_plural = "Mijozlar"
        constraints = [models.UniqueConstraint(fields=["shop", "telegram_id"], name="uniq_customer_per_shop")]

    def __str__(self) -> str:
        return self.full_name or self.username or str(self.telegram_id)


class Conversation(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="conversation")
    # Tugallanmagan buyurtma qoralamasi: {"items": [{"product_id", "quantity"}], "customer_name", "phone", "address"}
    draft = models.JSONField(default=dict, blank=True)
    awaiting_confirmation = models.BooleanField(default=False)
    needs_attention = models.BooleanField("Egasi e'tibori kerak", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Suhbat"
        verbose_name_plural = "Suhbatlar"
        ordering = ["-last_message_at"]

    def __str__(self) -> str:
        return f"Suhbat: {self.customer}"


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "Mijoz"), (ROLE_ASSISTANT, "Bot")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"
