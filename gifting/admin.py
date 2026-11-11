from django.contrib import admin

from .models import Cheer, Gift


class GiftInline(admin.TabularInline):
    model = Gift
    extra = 0
    can_delete = False
    fields = ("product_name", "recipient_email", "vendor", "price_cents", "status", "code")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cheer)
class CheerAdmin(admin.ModelAdmin):
    list_display = ("id", "sender", "status", "payment_method", "total_cents", "created_at")
    list_filter = ("status", "payment_method")
    inlines = [GiftInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("code", "product_name", "recipient_email", "vendor", "status", "expires_at")
    list_filter = ("status", "vendor")
    search_fields = ("code", "recipient_email", "product_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
