from django.urls import path

from . import portal

app_name = "portal"
urlpatterns = [
    path("", portal.dashboard, name="dashboard"),
    path("join/", portal.join, name="join"),
    path("products/", portal.products, name="products"),
    path("products/new/", portal.product_edit, name="product_new"),
    path("products/<int:pk>/", portal.product_edit, name="product_edit"),
    path("locations/", portal.locations, name="locations"),
    path("locations/new/", portal.location_edit, name="location_new"),
    path("locations/<int:pk>/", portal.location_edit, name="location_edit"),
    path("redeem/", portal.redeem, name="redeem"),
]
