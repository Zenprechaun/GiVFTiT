"""The gift lifecycle. Every state change and its ledger entry happen together.

  purchase  sender pays            -> value held in escrow, sender-paid fees held as unearned
  accept    recipient says yes     -> sender-paid fees become revenue
  deny      recipient says no      -> everything the sender paid goes to the sender's wallet
  redeem    vendor staff hand over -> vendor is owed value minus vendor-paid fees
  expire    nobody redeemed in time -> everything the sender paid goes to the sender's wallet
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from vendors.models import StaffMember
from wallet.models import Account, Payment
from wallet.payments import start_payment
from wallet.services import cr, dr, payable_for, post, system_account, wallet_for

from .models import CartItem, Cheer, Gift
from .notifications import notify_cheer_paid
from .pricing import price_cart_item


class GiftingError(Exception):
    """A request that cannot be carried out; the message is shown to the user."""


def _escrow():
    return system_account(Account.Kind.GIFT_ESCROW)


def _unearned():
    return system_account(Account.Kind.UNEARNED_FEES)


def _revenue():
    return system_account(Account.Kind.FEE_REVENUE)


# --- Purchase ------------------------------------------------------------------

def _check_ages(sender, recipients, items):
    age = max((item.product.minimum_age for item in items), default=0)
    if not age:
        return
    if not sender.is_at_least(age):
        raise GiftingError(
            f"Your cart has items restricted to ages {age}+. Add your date of birth to your profile to send them."
        )
    for user in recipients:
        if not user.is_at_least(age):
            raise GiftingError(
                f"{user.display_name} can't receive items restricted to ages {age}+ "
                "(no date of birth on file, or under age)."
            )


@transaction.atomic
def create_cheer(sender, recipients, emails, message, method):
    """Turn the sender's cart into a cheer.

    ``recipients`` are registered users; ``emails`` are people without an
    account yet, who receive their gifts when they sign up with that address.
    Returns (cheer, redirect_url). redirect_url is None for wallet payments,
    which complete immediately; for card payments it is where to send the
    customer to pay.
    """
    items = list(
        CartItem.objects.filter(user=sender).select_related("product__vendor__category", "product__category", "location")
    )
    if not items:
        raise GiftingError("Your cart is empty.")
    targets = [(user, user.email) for user in recipients] + [(None, email.lower()) for email in emails]
    if not targets:
        raise GiftingError("Choose at least one person to send this to.")
    for item in items:
        if not (item.product.is_active and item.product.vendor.is_active and item.location.is_active):
            raise GiftingError(f"{item.product.name} is no longer available. Remove it from your cart.")
    _check_ages(sender, recipients, items)

    cheer = Cheer.objects.create(sender=sender, message=message, payment_method=method)
    expires_at = timezone.now() + timedelta(days=settings.GIFT_EXPIRY_DAYS)
    gifts = []
    for user, email in targets:
        for item in items:
            unit = price_cart_item(item)
            for _ in range(item.quantity):
                gifts.append(
                    Gift(
                        cheer=cheer,
                        recipient=user,
                        recipient_email=email,
                        product=item.product,
                        vendor=item.product.vendor,
                        location=item.location,
                        product_name=item.product.name,
                        minimum_age=item.product.minimum_age,
                        fee_level=item.product.vendor.fee_level,
                        price_cents=unit.price,
                        tax_cents=unit.tax,
                        user_cheer_fee_cents=unit.user_cheer_fee,
                        user_vendor_fee_cents=unit.user_vendor_fee,
                        vendor_cheer_fee_cents=unit.vendor_cheer_fee,
                        vendor_vendor_fee_cents=unit.vendor_vendor_fee,
                        expires_at=expires_at,
                    )
                )
    Gift.objects.bulk_create(gifts)
    cheer.total_cents = sum(gift.sender_paid_cents for gift in gifts)
    cheer.save(update_fields=["total_cents"])

    if method == Cheer.Method.WALLET:
        # Raises InsufficientFunds (rolling everything back) if the wallet is short.
        return mark_cheer_paid(cheer, wallet_for(sender)), None

    payment, url = start_payment(
        sender, Payment.Purpose.CHEER, cheer.total_cents, f"{settings.SITE_NAME} cheer #{cheer.pk}"
    )
    cheer.payment = payment
    cheer.save(update_fields=["payment"])
    return cheer, url


@transaction.atomic
def mark_cheer_paid(cheer, source_account):
    cheer = Cheer.objects.select_for_update().get(pk=cheer.pk)
    if cheer.status == Cheer.Status.PAID:
        return cheer
    gifts = list(cheer.gifts.all())
    post(
        f"Cheer #{cheer.pk} purchased",
        [
            dr(source_account, cheer.total_cents),
            cr(_escrow(), sum(g.value_cents for g in gifts)),
            cr(_unearned(), sum(g.user_fees_cents for g in gifts)),
        ],
        reference=f"cheer:{cheer.pk}",
        idempotency_key=f"cheer-paid:{cheer.pk}",
    )
    cheer.status = Cheer.Status.PAID
    cheer.paid_at = timezone.now()
    cheer.save(update_fields=["status", "paid_at"])
    CartItem.objects.filter(user=cheer.sender).delete()
    transaction.on_commit(lambda: notify_cheer_paid(cheer.pk))
    return cheer


# --- After purchase --------------------------------------------------------------

def _lock(gift_id, allowed):
    gift = (
        Gift.objects.select_for_update(of=("self",))
        .select_related("cheer__sender", "vendor")
        .get(pk=gift_id)
    )
    if gift.cheer.status != Cheer.Status.PAID or gift.status not in allowed:
        raise GiftingError("This gift can no longer be changed.")
    return gift


def _require_recipient(gift, user):
    if gift.recipient_id != user.pk:
        raise GiftingError("This gift belongs to someone else.")


def _earn_fees(gift):
    """Ledger lines that turn the sender-paid fees into revenue (once)."""
    if gift.fees_earned:
        return []
    gift.fees_earned = True
    return [dr(_unearned(), gift.user_fees_cents), cr(_revenue(), gift.user_fees_cents)]


def _close(gift, status, **extra):
    gift.status = status
    gift.resolved_at = timezone.now()
    for field, value in extra.items():
        setattr(gift, field, value)
    gift.save()


@transaction.atomic
def accept(gift_id, user):
    gift = _lock(gift_id, [Gift.Status.PENDING])
    _require_recipient(gift, user)
    if gift.minimum_age and not user.is_at_least(gift.minimum_age):
        raise GiftingError(
            f"This gift is restricted to ages {gift.minimum_age}+. "
            "Add your date of birth to your profile, or decline it."
        )
    lines = _earn_fees(gift)
    post(f"Gift {gift.code} accepted", lines, reference=f"gift:{gift.pk}", idempotency_key=f"gift-accept:{gift.pk}")
    gift.status = Gift.Status.ACCEPTED
    gift.save()
    return gift


def _return_to_sender(gift, status, reason):
    # Fees go back too: from revenue if the gift had been accepted, otherwise
    # from the unearned-fees holding account.
    fee_account = _revenue() if gift.fees_earned else _unearned()
    post(
        f"Gift {gift.code} {reason}, returned to sender",
        [
            dr(_escrow(), gift.value_cents),
            dr(fee_account, gift.user_fees_cents),
            cr(wallet_for(gift.cheer.sender), gift.sender_paid_cents),
        ],
        reference=f"gift:{gift.pk}",
        idempotency_key=f"gift-return:{gift.pk}",
    )
    _close(gift, status)


@transaction.atomic
def deny(gift_id, user):
    gift = _lock(gift_id, [Gift.Status.PENDING])
    _require_recipient(gift, user)
    _return_to_sender(gift, Gift.Status.DENIED, "declined")
    return gift


@transaction.atomic
def redeem(gift_id, staff_user):
    """Vendor staff hand over the goods; the vendor is now owed for the gift."""
    gift = _lock(gift_id, [Gift.Status.ACCEPTED])
    if not StaffMember.objects.filter(vendor=gift.vendor, user=staff_user).exists():
        raise GiftingError("You are not on this vendor's staff.")
    post(
        f"Gift {gift.code} redeemed at {gift.vendor.name}",
        _earn_fees(gift)
        + [
            dr(_escrow(), gift.value_cents),
            cr(payable_for(gift.vendor), gift.vendor_net_cents),
            cr(_revenue(), gift.vendor_fees_cents),
        ],
        reference=f"gift:{gift.pk}",
        idempotency_key=f"gift-redeem:{gift.pk}",
    )
    _close(gift, Gift.Status.REDEEMED, redeemed_by=staff_user)
    return gift


def expire_due(now=None):
    """Close gifts past their expiry date. Returns how many were closed."""
    now = now or timezone.now()
    due = Gift.objects.filter(
        status__in=Gift.OPEN, expires_at__lte=now, cheer__status=Cheer.Status.PAID
    ).values_list("pk", flat=True)
    count = 0
    for gift_id in list(due):
        with transaction.atomic():
            try:
                gift = _lock(gift_id, Gift.OPEN)
            except GiftingError:
                continue
            _return_to_sender(gift, Gift.Status.EXPIRED, "expired")
            count += 1
    return count
