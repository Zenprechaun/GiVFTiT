from collections import defaultdict

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse


def notify_cheer_paid(cheer_id):
    """Email each recipient of a paid cheer."""
    from .models import Cheer

    cheer = Cheer.objects.select_related("sender").get(pk=cheer_id)
    by_email = defaultdict(list)
    for gift in cheer.gifts.select_related("vendor", "recipient"):
        by_email[gift.recipient_email].append(gift)
    sender = cheer.sender.display_name
    for email, gifts in by_email.items():
        registered = gifts[0].recipient_id is not None
        path = reverse("gifting:cheers") if registered else f"{reverse('accounts:signup')}?email={email}"
        items = "\n".join(f"  - {g.product_name} from {g.vendor.name}" for g in gifts)
        note = f'\n"{cheer.message}"\n' if cheer.message else ""
        action = "See your gifts" if registered else "Create your account to claim them"
        send_mail(
            f"{sender} sent you a cheer on {settings.SITE_NAME}",
            f"{sender} sent you:\n{items}\n{note}\n{action}: {settings.SITE_URL}{path}\n",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=True,
        )
