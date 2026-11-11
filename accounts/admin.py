from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Address, User


@admin.register(User)
class PlatformUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("phone", "date_of_birth", "is_profile_public")}),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_staff")


admin.site.register(Address)
