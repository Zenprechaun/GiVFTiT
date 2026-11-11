import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Payment, Posting
from .payments import mark_paid, start_payment
from .services import wallet_for

log = logging.getLogger(__name__)


@login_required
def wallet(request):
    account = wallet_for(request.user)
    postings = (
        Posting.objects.filter(account=account).select_related("entry", "account").order_by("-entry__created_at", "-id")[:50]
    )
    return render(
        request,
        "wallet/wallet.html",
        {"balance": account.balance(), "postings": postings, "max_topup": settings.MAX_TOPUP_CENTS},
    )


@login_required
@require_POST
def topup(request):
    try:
        cents = int((Decimal(request.POST.get("amount", "")) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        cents = 0
    if not 100 <= cents <= settings.MAX_TOPUP_CENTS:
        messages.error(request, "Enter an amount between $1 and the top-up limit.")
        return redirect("wallet:wallet")
    _, url = start_payment(request.user, Payment.Purpose.TOPUP, cents, f"{settings.SITE_NAME} wallet top-up")
    return redirect(url)


@login_required
def fake_pay(request, pk):
    """Development stand-in for Stripe's hosted payment page."""
    if settings.PAYMENTS_PROVIDER != "fake":
        raise Http404
    payment = get_object_or_404(Payment, pk=pk, user=request.user, provider="fake")
    if request.method == "POST":
        if "pay" in request.POST:
            mark_paid(payment.pk)
        return redirect("wallet:payment_done", pk=payment.pk)
    return render(request, "wallet/fake_pay.html", {"payment": payment})


@login_required
def payment_done(request, pk):
    payment = get_object_or_404(Payment, pk=pk, user=request.user)
    return render(request, "wallet/payment_done.html", {"payment": payment})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Stripe calls this when a Checkout payment completes. The signature is verified."""
    import stripe

    try:
        event = stripe.Webhook.construct_event(
            request.body, request.headers.get("Stripe-Signature", ""), settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:  # bad payload or bad signature
        return HttpResponseBadRequest("invalid signature")

    if event.type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session = event.data.object
        if session.payment_status == "paid":
            payment = Payment.objects.filter(
                pk=session.client_reference_id, provider="stripe", provider_ref=session.id
            ).first()
            if payment is None:
                log.warning("Stripe session %s matches no payment", session.id)
            elif session.amount_total != payment.amount_cents:
                log.error("Stripe session %s amount mismatch for payment %s", session.id, payment.pk)
            else:
                mark_paid(payment.pk)
    return HttpResponse(status=200)
