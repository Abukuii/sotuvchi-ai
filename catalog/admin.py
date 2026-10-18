from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "category", "price", "stock", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "sku", "shop__name")
    list_select_related = ("shop",)
