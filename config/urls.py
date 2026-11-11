from django.contrib import admin
from django.urls import include, path

from vendors import views as vendor_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", vendor_views.browse, name="home"),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("friends/", include("social.urls")),
    path("vendors/", include("vendors.urls")),
    path("portal/", include("vendors.portal_urls")),
    path("wallet/", include("wallet.urls")),
    path("", include("gifting.urls")),
]
