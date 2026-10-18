from django.contrib import admin

from .models import Shop


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    # Token maydonlari editable=False: admin da ko'rinmaydi va tahrirlanmaydi
    list_display = ("name", "owner", "is_active", "bot_username", "has_token", "created_at")
    list_filter = ("is_active", "default_language")
    search_fields = ("name", "owner__username", "bot_username")

    @admin.display(boolean=True, description="Token bor")
    def has_token(self, obj):
        return obj.has_token
