from django.contrib import admin

from .models import Conversation, Customer, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    can_delete = False
    readonly_fields = ("role", "text", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "shop", "username", "language", "created_at")
    search_fields = ("full_name", "username", "shop__name")
    list_select_related = ("shop",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("customer", "needs_attention", "awaiting_confirmation", "last_message_at")
    list_filter = ("needs_attention",)
    inlines = [MessageInline]
    readonly_fields = ("customer", "draft", "created_at", "last_message_at")
