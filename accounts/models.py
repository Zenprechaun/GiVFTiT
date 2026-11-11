from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A person on the platform: sender, receiver, and/or vendor staff."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_profile_public = models.BooleanField(
        default=True, help_text="Whether other members can find this profile."
    )

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def age(self):
        born = self.date_of_birth
        if not born:
            return None
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    def is_at_least(self, years):
        return self.age is not None and self.age >= years


class Address(models.Model):
    class Kind(models.TextChoices):
        MAILING = "mailing", "Mailing"
        SHIPPING = "shipping", "Shipping"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SHIPPING)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=2, default="US")
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.line1}, {self.city}"
