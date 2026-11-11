from django.contrib import admin

from .models import Category, Location, Product, StaffMember, Vendor


class LocationInline(admin.TabularInline):
    model = Location
    extra = 0


class StaffInline(admin.TabularInline):
    model = StaffMember
    extra = 0


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "fee_level", "is_active")
    list_filter = ("category", "fee_level", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [LocationInline, StaffInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "vendor", "price_cents", "source", "is_active")
    list_filter = ("source", "is_active")
    search_fields = ("name", "vendor__name")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "minimum_age")
    prepopulated_fields = {"slug": ("name",)}
