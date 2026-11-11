from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import validate_email

from social.models import BuddyGroup, friends_of

from .models import Cheer


class CheckoutForm(forms.Form):
    friends = forms.ModelMultipleChoiceField(
        queryset=None, required=False, widget=forms.CheckboxSelectMultiple
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=None, required=False, widget=forms.CheckboxSelectMultiple, label="Buddy groups"
    )
    emails = forms.CharField(
        required=False,
        label="Or send by email",
        help_text="Comma-separated. People without an account get an invitation to claim their gift.",
    )
    message = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), max_length=1000)
    method = forms.ChoiceField(choices=Cheer.Method.choices, widget=forms.RadioSelect, label="Pay with")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["friends"].queryset = friends_of(user)
        self.fields["groups"].queryset = BuddyGroup.objects.filter(owner=user)
        self.fields["friends"].label_from_instance = lambda u: u.display_name

    def clean_emails(self):
        emails = {e.strip().lower() for e in self.cleaned_data["emails"].split(",") if e.strip()}
        for email in emails:
            validate_email(email)
        return emails

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        User = get_user_model()
        users = {u.pk: u for u in data["friends"]}
        for group in data["groups"]:
            users.update({u.pk: u for u in group.members.all()})
        # An email that belongs to a member is treated as that member.
        emails = set(data["emails"])
        for member in User.objects.filter(email__in=emails):
            users[member.pk] = member
            emails.discard(member.email)
        users.pop(self.user.pk, None)
        if not users and not emails:
            raise forms.ValidationError("Choose at least one person to send this to.")
        data["recipient_users"] = list(users.values())
        data["recipient_emails"] = sorted(emails)
        return data
