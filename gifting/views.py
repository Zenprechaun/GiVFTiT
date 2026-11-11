from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from vendors.models import Location, Product
from wallet.services import InsufficientFunds, wallet_for

from . import services
from .forms import CheckoutForm
from .models import CartItem, Cheer, Gift
from .pricing import price_cart_item


def _cart(user):
    items = list(
        CartItem.objects.filter(user=user).select_related("product__vendor__category", "product__category", "location")
    )
    for item in items:
        item.unit = price_cart_item(item)
        item.line_total = item.unit.sender_total * item.quantity
    return items, sum(item.line_total for item in items)


@login_required
def cart(request):
    items, total = _cart(request.user)
    return render(request, "gifting/cart.html", {"items": items, "total": total})


@login_required
@require_POST
def cart_add(request):
    product = get_object_or_404(Product, pk=request.POST.get("product"), is_active=True, vendor__is_active=True)
    location = get_object_or_404(Location, pk=request.POST.get("location"), vendor=product.vendor, is_active=True)
    try:
        quantity = max(1, min(20, int(request.POST.get("quantity", 1))))
    except ValueError:
        quantity = 1
    item, created = CartItem.objects.get_or_create(
        user=request.user, product=product, location=location, defaults={"quantity": quantity}
    )
    if not created:
        item.quantity = min(20, item.quantity + quantity)
        item.save(update_fields=["quantity"])
    messages.success(request, f"{product.name} added to your cart.")
    return redirect("gifting:cart")


@login_required
@require_POST
def cart_remove(request, pk):
    CartItem.objects.filter(pk=pk, user=request.user).delete()
    return redirect("gifting:cart")


@login_required
def checkout(request):
    items, total = _cart(request.user)
    if not items:
        return redirect("gifting:cart")
    form = CheckoutForm(request.user, request.POST or None, initial={"method": Cheer.Method.CARD})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            cheer, pay_url = services.create_cheer(
                request.user, data["recipient_users"], data["recipient_emails"], data["message"], data["method"]
            )
        except InsufficientFunds:
            form.add_error("method", "Your wallet balance doesn't cover this. Top up or pay by card.")
        except services.GiftingError as error:
            form.add_error(None, str(error))
        else:
            if pay_url:
                return redirect(pay_url)
            messages.success(request, "Cheer sent!")
            return redirect("gifting:cheers")
    return render(
        request,
        "gifting/checkout.html",
        {"form": form, "items": items, "total": total, "balance": wallet_for(request.user).balance()},
    )


@login_required
def cheers(request):
    received = (
        Gift.objects.filter(recipient=request.user, cheer__status=Cheer.Status.PAID)
        .select_related("cheer__sender", "vendor", "location")
        .order_by("-cheer__paid_at", "-id")
    )
    sent = (
        Cheer.objects.filter(sender=request.user, status=Cheer.Status.PAID)
        .prefetch_related("gifts__vendor", "gifts__recipient")
    )
    return render(
        request,
        "gifting/cheers.html",
        {
            "open_gifts": [g for g in received if g.is_open],
            "past_gifts": [g for g in received if not g.is_open],
            "sent": sent,
        },
    )


@login_required
def gift(request, pk):
    gift = get_object_or_404(
        Gift.objects.select_related("cheer__sender", "vendor", "location"),
        Q(recipient=request.user) | Q(cheer__sender=request.user),
        pk=pk,
        cheer__status=Cheer.Status.PAID,
    )
    return render(request, "gifting/gift.html", {"gift": gift, "is_recipient": gift.recipient_id == request.user.pk})


@login_required
@require_POST
def gift_action(request, pk, action):
    actions = {"accept": services.accept, "deny": services.deny}
    done = {"accept": "Gift accepted.", "deny": "Gift declined and returned to the sender."}
    if action in actions:
        try:
            actions[action](pk, request.user)
            messages.success(request, done[action])
        except Gift.DoesNotExist:
            messages.error(request, "Gift not found.")
        except services.GiftingError as error:
            messages.error(request, str(error))
    return redirect("gifting:cheers")
