from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Friendship, Invitation


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def connect_inviters_on_signup(sender, instance, created, **kwargs):
    """When an invited person signs up, they become friends with whoever invited them."""
    if not created or not instance.email:
        return
    pending = Invitation.objects.filter(email__iexact=instance.email, accepted_at__isnull=True)
    for invitation in pending.select_related("inviter"):
        Friendship.objects.update_or_create(
            from_user=invitation.inviter,
            to_user=instance,
            defaults={"status": Friendship.Status.ACCEPTED},
        )
    pending.update(accepted_at=timezone.now())
