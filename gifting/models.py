import secrets

from django.conf import settings
from django.db import models

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alikes (0/O, 1/I/L)


def new_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))


class CartItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey("vendors.Product", on_delete=models.CASCADE)
    location = models.ForeignKey("vendors.Location", on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product", "location"], name="one_cart_line_per_product")
        ]


class Cheer(models.Model):
    """One send: a sender gives one or more items to one or more people."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID = "paid", "Paid"

    class Method(models.TextChoices):
        WALLET = "wallet", "Wallet balance"
        CARD = "card", "Card"

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cheers_sent")
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT)
    payment_method = models.CharField(max_length=10, choices=Method.choices)
    payment = models.OneToOneField(
        "wallet.Payment", null=True, blank=True, on_delete=models.PROTECT, related_name="cheer"
    )
    total_cents = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cheer #{self.pk} from {self.sender}"


class Gift(models.Model):
    """One unit of one item for one recipient. Prices and fees are frozen at purchase."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for a response"
        ACCEPTED = "accepted", "Accepted"
        DENIED = "denied", "Declined (returned to sender)"
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED = "expired", "Expired (returned to sender)"

    OPEN = (Status.PENDING, Status.ACCEPTED)

    cheer = models.ForeignKey(Cheer, on_delete=models.PROTECT, related_name="gifts")
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="gifts_received"
    )
    recipient_email = models.EmailField()
    product = models.ForeignKey("vendors.Product", null=True, on_delete=models.SET_NULL)
    vendor = models.ForeignKey("vendors.Vendor", on_delete=models.PROTECT, related_name="gifts")
    location = models.ForeignKey("vendors.Location", on_delete=models.PROTECT, related_name="gifts")
    product_name = models.CharField(max_length=200)
    minimum_age = models.PositiveSmallIntegerField(default=0)
    fee_level = models.CharField(max_length=20)

    # All amounts are cents per unit.
    price_cents = models.PositiveIntegerField()
    tax_cents = models.PositiveIntegerField(default=0)
    user_cheer_fee_cents = models.PositiveIntegerField(default=0)
    user_vendor_fee_cents = models.PositiveIntegerField(default=0)
    vendor_cheer_fee_cents = models.PositiveIntegerField(default=0)
    vendor_vendor_fee_cents = models.PositiveIntegerField(default=0)
    fees_earned = models.BooleanField(default=False)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    code = models.CharField(max_length=12, unique=True, default=new_code)
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="redemptions"
    )

    class Meta:
        ordering = ["-id"]

    @property
    def value_cents(self):
        """What the gift is worth to the recipient: item price plus tax."""
        return self.price_cents + self.tax_cents

    @property
    def user_fees_cents(self):
        return self.user_cheer_fee_cents + self.user_vendor_fee_cents

    @property
    def vendor_fees_cents(self):
        return self.vendor_cheer_fee_cents + self.vendor_vendor_fee_cents

    @property
    def sender_paid_cents(self):
        return self.value_cents + self.user_fees_cents

    @property
    def vendor_net_cents(self):
        return self.value_cents - self.vendor_fees_cents

    @property
    def is_open(self):
        return self.status in self.OPEN

    @property
    def display_code(self):
        return f"{self.code[:5]}-{self.code[5:]}"

    def __str__(self):
        return f"{self.product_name} for {self.recipient_email}"
