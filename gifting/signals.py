from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from wallet.models import Account, Payment
from wallet.payments import payment_paid
from wallet.services import system_account

from .models import Gift
from .services import mark_cheer_paid


@receiver(payment_paid)
def release_cheer_when_card_payment_clears(sender, payment, **kwargs):
    if payment.purpose == Payment.Purpose.CHEER:
        mark_cheer_paid(payment.cheer, system_account(Account.Kind.PROCESSOR_CLEARING))


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def claim_gifts_on_signup(sender, instance, created, **kwargs):
    """Gifts sent to an email address attach to the account created with it."""
    if created and instance.email:
        Gift.objects.filter(recipient__isnull=True, recipient_email__iexact=instance.email).update(
            recipient=instance
        )
