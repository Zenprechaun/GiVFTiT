from django import forms

from .models import Category, FeeLevel, Location, Product


class VendorSignupForm(forms.Form):
    name = forms.CharField(max_length=200, label="Business name")
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.all())
    fee_level = forms.ChoiceField(choices=FeeLevel.choices)
    location_name = forms.CharField(max_length=200, label="First location name", initial="Main location")
    address = forms.CharField(max_length=200, required=False)
    city = forms.CharField(max_length=100, required=False)
    state = forms.CharField(max_length=100, required=False)
    postal_code = forms.CharField(max_length=20, required=False)
    tax_rate = forms.DecimalField(min_value=0, max_value=30, decimal_places=3, initial=0, label="Sales tax %")


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ("name", "address", "city", "state", "postal_code", "tax_rate", "is_active")


class ProductForm(forms.ModelForm):
    price = forms.DecimalField(min_value=0, max_digits=8, decimal_places=2, label="Price ($)")

    class Meta:
        model = Product
        fields = ("name", "description", "category", "fulfilment", "image_url", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["price"].initial = self.instance.price_cents / 100

    def save(self, commit=True):
        self.instance.price_cents = int(self.cleaned_data["price"] * 100)
        return super().save(commit)
