from django.urls import path

from . import views

app_name = "wallet"
urlpatterns = [
    path("", views.wallet, name="wallet"),
    path("topup/", views.topup, name="topup"),
    path("pay/<int:pk>/", views.fake_pay, name="fake_pay"),
    path("payments/<int:pk>/", views.payment_done, name="payment_done"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
