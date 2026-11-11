from django.conf import settings
from django.db import models
from django.utils.text import slugify


class FeeLevel(models.TextChoices):
    """Who pays the platform's two fees. Names carried over from the original app."""

    CHARITABLE = "charitable", "Charitable (sender pays both fees)"
    ZERO_MARGIN = "zero_margin", "Zero margin (vendor pays the vendor fee)"
    MAX_ATTRACTION = "max_attraction", "Maximum attraction (vendor pays both fees)"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=110, unique=True)
    minimum_age = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minimum age to send or receive gifts in this category (21 for alcohol).",
    )

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


def unique_slug(model, text):
    base = slugify(text)[:90] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=110, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="vendors")
    fee_level = models.CharField(max_length=20, choices=FeeLevel.choices, default=FeeLevel.CHARITABLE)
    website = models.URLField(blank=True)
    stripe_account_id = models.CharField(
        max_length=64, blank=True, help_text="Stripe Connect account used for payouts (set later)."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Vendor, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Location(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    tax_rate = models.DecimalField(
        max_digits=6, decimal_places=3, default=0, help_text="Sales tax as a percentage, e.g. 7.25"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.vendor.name} - {self.name}"


class StaffMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff (redeem only)"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="staff")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_roles")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["vendor", "user"], name="unique_staff_per_vendor")]

    @property
    def can_manage(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER)

    def __str__(self):
        return f"{self.user} @ {self.vendor} ({self.role})"


class Product(models.Model):
    class Fulfilment(models.TextChoices):
        IN_PERSON = "in_person", "In person"
        DELIVERY = "delivery", "Delivery"
        SHIPMENT = "shipment", "Shipment"
        DIGITAL = "digital", "Digital"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=True, blank=True, related_name="products",
        help_text="Leave empty to use the vendor's category.",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField()
    fulfilment = models.CharField(max_length=10, choices=Fulfilment.choices, default=Fulfilment.IN_PERSON)
    image_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    # Where the product came from: "manual" (typed into the portal) or the name
    # of a catalog connector. external_id is the product's id in that system.
    source = models.CharField(max_length=30, default="manual")
    external_id = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "source", "external_id"],
                condition=~models.Q(external_id=""),
                name="unique_external_product",
            )
        ]

    @property
    def minimum_age(self):
        ages = [self.vendor.category.minimum_age]
        if self.category_id:
            ages.append(self.category.minimum_age)
        return max(ages)

    def __str__(self):
        return self.name
