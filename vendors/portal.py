"""The vendor portal: where a business manages its page and redeems gifts."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from gifting import services as gifting
from gifting.models import Cheer, Gift
from wallet.models import Posting
from wallet.services import payable_for

from .forms import LocationForm, ProductForm, VendorSignupForm
from .models import Location, Product, StaffMember, Vendor


def staff_required(manage=False):
    """Require the user to be on a vendor's staff; ``manage`` needs owner or manager."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            membership = (
                StaffMember.objects.filter(user=request.user, vendor__is_active=True)
                .select_related("vendor__category")
                .first()
            )
            if membership is None:
                return redirect("portal:join")
            if manage and not membership.can_manage:
                messages.error(request, "Only owners and managers can do that.")
                return redirect("portal:dashboard")
            request.vendor, request.membership = membership.vendor, membership
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


@login_required
def join(request):
    if StaffMember.objects.filter(user=request.user).exists():
        return redirect("portal:dashboard")
    form = VendorSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            vendor = Vendor.objects.create(
                name=data["name"], description=data["description"],
                category=data["category"], fee_level=data["fee_level"],
            )
            Location.objects.create(
                vendor=vendor, name=data["location_name"], address=data["address"], city=data["city"],
                state=data["state"], postal_code=data["postal_code"], tax_rate=data["tax_rate"],
            )
            StaffMember.objects.create(vendor=vendor, user=request.user, role=StaffMember.Role.OWNER)
        messages.success(request, "Your business page is set up. Add your first product.")
        return redirect("portal:products")
    return render(request, "portal/join.html", {"form": form})


@staff_required()
def dashboard(request):
    vendor = request.vendor
    account = payable_for(vendor)
    gifts = Gift.objects.filter(vendor=vendor, cheer__status=Cheer.Status.PAID)
    return render(
        request,
        "portal/dashboard.html",
        {
            "vendor": vendor,
            "balance": account.balance(),
            "outstanding": gifts.filter(status__in=Gift.OPEN).count(),
            "redeemed": gifts.filter(status=Gift.Status.REDEEMED).select_related("location")[:20],
            "postings": Posting.objects.filter(account=account).select_related("entry", "account")
            .order_by("-entry__created_at", "-id")[:20],
        },
    )


@staff_required(manage=True)
def products(request):
    return render(request, "portal/products.html", {"vendor": request.vendor, "products": request.vendor.products.all()})


@staff_required(manage=True)
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk, vendor=request.vendor) if pk else Product(vendor=request.vendor)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product saved.")
        return redirect("portal:products")
    return render(request, "portal/form.html", {"form": form, "title": "Edit product" if pk else "Add product"})


@staff_required(manage=True)
def locations(request):
    return render(request, "portal/locations.html", {"vendor": request.vendor, "locations": request.vendor.locations.all()})


@staff_required(manage=True)
def location_edit(request, pk=None):
    location = get_object_or_404(Location, pk=pk, vendor=request.vendor) if pk else Location(vendor=request.vendor)
    form = LocationForm(request.POST or None, instance=location)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Location saved.")
        return redirect("portal:locations")
    return render(request, "portal/form.html", {"form": form, "title": "Edit location" if pk else "Add location"})


@staff_required()
def redeem(request):
    """Look a gift up by its code, then confirm handing it over."""
    code = (request.POST.get("code") or request.GET.get("code") or "").replace("-", "").replace(" ", "").upper()
    gift = None
    if code:
        gift = (
            Gift.objects.filter(code=code, vendor=request.vendor, cheer__status=Cheer.Status.PAID)
            .select_related("location", "recipient", "cheer__sender")
            .first()
        )
        if gift is None:
            messages.error(request, "No gift with that code for this business.")
        elif request.method == "POST" and "confirm" in request.POST:
            try:
                gifting.redeem(gift.pk, request.user)
                messages.success(request, f"Redeemed: {gift.product_name}.")
                return redirect("portal:redeem")
            except gifting.GiftingError as error:
                messages.error(request, str(error))
    return render(request, "portal/redeem.html", {"gift": gift, "code": code})
