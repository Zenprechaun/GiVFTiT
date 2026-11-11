from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User

_DATE = forms.DateInput(attrs={"type": "date"})


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "date_of_birth")
        widgets = {"date_of_birth": _DATE}
        help_texts = {"date_of_birth": "Needed to send or receive age-restricted gifts."}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone", "date_of_birth", "is_profile_public")
        widgets = {"date_of_birth": _DATE}
