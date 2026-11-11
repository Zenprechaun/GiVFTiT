from django.contrib import admin

from .models import Account, JournalEntry, Payment, Posting


class ReadOnlyAdmin(admin.ModelAdmin):
    """The ledger is append-only: it can be inspected in the admin, never edited."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PostingInline(admin.TabularInline):
    model = Posting
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(ReadOnlyAdmin):
    list_display = ("id", "created_at", "description", "reference")
    search_fields = ("description", "reference")
    inlines = [PostingInline]


@admin.register(Account)
class AccountAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "kind", "balance")
    list_filter = ("kind",)


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("id", "user", "purpose", "amount_cents", "status", "provider", "created_at")
    list_filter = ("status", "purpose", "provider")
