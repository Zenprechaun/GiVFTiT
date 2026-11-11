from django.urls import path

from . import views

app_name = "gifting"
urlpatterns = [
    path("cart/", views.cart, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("cheers/", views.cheers, name="cheers"),
    path("gifts/<int:pk>/", views.gift, name="gift"),
    path("gifts/<int:pk>/<str:action>/", views.gift_action, name="gift_action"),
]
