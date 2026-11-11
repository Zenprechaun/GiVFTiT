"""Posting to the ledger. This is the only code that creates journal entries."""
from collections import defaultdict, namedtuple

from django.db import transaction

from .models import Account, JournalEntry, Posting

Line = namedtuple("Line", "account amount")  # amount: +debit / -credit, in cents


class InsufficientFunds(Exception):
    pass


def dr(account, cents):
    return Line(account, cents)


def cr(account, cents):
    return Line(account, -cents)


def system_account(kind):
    return Account.objects.get_or_create(kind=kind, user=None, vendor=None)[0]


def wallet_for(user):
    return Account.objects.get_or_create(kind=Account.Kind.USER_WALLET, user=user)[0]


def payable_for(vendor):
    return Account.objects.get_or_create(kind=Account.Kind.VENDOR_PAYABLE, vendor=vendor)[0]


@transaction.atomic
def post(description, lines, *, reference="", idempotency_key=None):
    """Record one balanced journal entry.

    Zero-amount lines are dropped. A wallet can never be taken below zero: the
    wallet row is locked and its balance checked before the entry is written.
    Passing an ``idempotency_key`` makes a repeated call a no-op.
    """
    lines = [line for line in lines if line.amount]
    if not lines:
        return None
    if sum(line.amount for line in lines) != 0:
        raise ValueError(f"Unbalanced journal entry: {description}")
    if idempotency_key:
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    wallet_debits = defaultdict(int)
    for line in lines:
        if line.account.kind == Account.Kind.USER_WALLET and line.amount > 0:
            wallet_debits[line.account.pk] += line.amount
    for account_id, amount in wallet_debits.items():
        account = Account.objects.select_for_update().get(pk=account_id)
        if account.balance() < amount:
            raise InsufficientFunds("Not enough wallet balance.")

    entry = JournalEntry.objects.create(
        description=description[:200], reference=reference, idempotency_key=idempotency_key
    )
    Posting.objects.bulk_create(
        Posting(entry=entry, account=line.account, amount=line.amount) for line in lines
    )
    return entry
