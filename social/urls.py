from django.urls import path

from . import views

app_name = "social"
urlpatterns = [
    path("", views.friends, name="friends"),
    path("requests/<int:pk>/<str:action>/", views.respond, name="respond"),
    path("groups/new/", views.group_create, name="group_create"),
    path("groups/<int:pk>/", views.group, name="group"),
]
