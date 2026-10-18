from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "name", "unit_price", "quantity")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "shop", "customer_name", "phone", "total", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("customer_name", "phone", "shop__name")
    inlines = [OrderItemInline]
    readonly_fields = ("shop", "customer", "total", "created_at")
