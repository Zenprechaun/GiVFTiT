"""Card payments.

The site never sees card numbers. With Stripe, the customer pays on Stripe's
hosted Checkout page and Stripe tells us the result through a signed webhook.
The "fake" provider stands in for Stripe during development and tests.
"""
from django.conf import settings
from django.db import transaction
from django.dispatch import Signal
from django.urls import reverse
from django.utils import timezone

from .models import Account, Payment
from .services import cr, dr, post, system_account, wallet_for

# Sent (inside the transaction) the first time a payment is confirmed paid.
payment_paid = Signal()


class FakeProvider:
    name = "fake"

    def start(self, payment, description):
        return reverse("wallet:fake_pay", args=[payment.pk])


class StripeProvider:
    name = "stripe"

    def start(self, payment, description):
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        done = f"{settings.SITE_URL}{reverse('wallet:payment_done', args=[payment.pk])}"
        session = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(payment.pk),
            customer_email=payment.user.email,
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": settings.CURRENCY,
                        "unit_amount": payment.amount_cents,
                        "product_data": {"name": description[:120]},
                    },
                }
            ],
            success_url=done,
            cancel_url=done,
        )
        payment.provider_ref = session.id
        payment.save(update_fields=["provider_ref"])
        return session.url


def get_provider():
    return StripeProvider() if settings.PAYMENTS_PROVIDER == "stripe" else FakeProvider()


def start_payment(user, purpose, amount_cents, description):
    """Create a Payment and return (payment, URL to send the customer to)."""
    provider = get_provider()
    payment = Payment.objects.create(
        user=user, purpose=purpose, amount_cents=amount_cents, provider=provider.name
    )
    return payment, provider.start(payment, description)


@transaction.atomic
def mark_paid(payment_id):
    """Confirm a payment. Safe to call more than once (webhooks can repeat)."""
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.status == Payment.Status.PAID:
        return payment
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "paid_at"])
    if payment.purpose == Payment.Purpose.TOPUP:
        post(
            "Wallet top-up by card",
            [
                dr(system_account(Account.Kind.PROCESSOR_CLEARING), payment.amount_cents),
                cr(wallet_for(payment.user), payment.amount_cents),
            ],
            reference=f"payment:{payment.pk}",
            idempotency_key=f"topup:{payment.pk}",
        )
    payment_paid.send(sender=Payment, payment=payment)
    return payment
