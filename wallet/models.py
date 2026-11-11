"""Double-entry ledger and payments.

All money is stored as integer cents. Every movement of money is a
JournalEntry whose Postings sum to zero (debits positive, credits negative),
so the books always balance and every balance can be recomputed from history.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q, Sum


class Account(models.Model):
    class Kind(models.TextChoices):
        PROCESSOR_CLEARING = "processor_clearing", "Card processor clearing (money received)"
        USER_WALLET = "user_wallet", "User wallet"
        GIFT_ESCROW = "gift_escrow", "Gifts paid for but not yet redeemed"
        UNEARNED_FEES = "unearned_fees", "Fees collected but not yet earned"
        FEE_REVENUE = "fee_revenue", "Fee revenue"
        VENDOR_PAYABLE = "vendor_payable", "Owed to vendor"

    # Asset accounts grow with debits; every other kind grows with credits.
    DEBIT_NORMAL = {Kind.PROCESSOR_CLEARING}

    kind = models.CharField(max_length=20, choices=Kind.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_accounts"
    )
    vendor = models.ForeignKey(
        "vendors.Vendor", null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_accounts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind"], condition=Q(user__isnull=True, vendor__isnull=True), name="one_system_account_per_kind"
            ),
            models.UniqueConstraint(fields=["kind", "user"], condition=Q(user__isnull=False), name="one_account_per_user"),
            models.UniqueConstraint(
                fields=["kind", "vendor"], condition=Q(vendor__isnull=False), name="one_account_per_vendor"
            ),
        ]

    def balance(self):
        total = self.postings.aggregate(total=Sum("amount"))["total"] or 0
        return total if self.kind in self.DEBIT_NORMAL else -total

    def __str__(self):
        owner = self.user or self.vendor
        return f"{self.get_kind_display()}" + (f" - {owner}" if owner else "")


class JournalEntry(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=200)
    reference = models.CharField(max_length=60, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True)

    class Meta:
        verbose_name_plural = "journal entries"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"#{self.pk} {self.description}"


class Posting(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="postings")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="postings")
    amount = models.BigIntegerField(help_text="Cents. Positive = debit, negative = credit.")

    @property
    def change(self):
        """Effect on the account's balance, in the account's natural direction."""
        return self.amount if self.account.kind in Account.DEBIT_NORMAL else -self.amount


class Payment(models.Model):
    """A card payment: either a wallet top-up or the purchase of a cheer."""

    class Purpose(models.TextChoices):
        TOPUP = "topup", "Wallet top-up"
        CHEER = "cheer", "Cheer purchase"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=20)
    provider_ref = models.CharField(max_length=200, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment #{self.pk} {self.get_purpose_display()} {self.amount_cents}c ({self.status})"
