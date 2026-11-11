"""Public catalog pages: browse vendors and see what they offer."""
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from .models import Category, Vendor


def browse(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    vendors = (
        Vendor.objects.filter(is_active=True)
        .select_related("category")
        .annotate(product_count=Count("products", filter=Q(products__is_active=True)))
        .filter(product_count__gt=0)
    )
    if query:
        vendors = vendors.filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(products__name__icontains=query)
        ).distinct()
    if category:
        vendors = vendors.filter(category__slug=category)
    return render(
        request,
        "vendors/browse.html",
        {"vendors": vendors[:60], "categories": Category.objects.all(), "query": query, "category": category},
    )


def vendor_detail(request, slug):
    vendor = get_object_or_404(Vendor.objects.select_related("category"), slug=slug, is_active=True)
    return render(
        request,
        "vendors/detail.html",
        {
            "vendor": vendor,
            "products": vendor.products.filter(is_active=True).select_related("category", "vendor__category"),
            "locations": vendor.locations.filter(is_active=True),
        },
    )
