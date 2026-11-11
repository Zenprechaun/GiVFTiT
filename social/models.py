import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

User = settings.AUTH_USER_MODEL


class Friendship(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_sent")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_received")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="unique_friend_request"),
            models.CheckConstraint(condition=~Q(from_user=models.F("to_user")), name="no_self_friendship"),
        ]

    def __str__(self):
        return f"{self.from_user} -> {self.to_user} ({self.status})"


def friends_of(user):
    """All users with an accepted friendship with ``user``, in either direction."""
    from django.contrib.auth import get_user_model

    accepted = Friendship.Status.ACCEPTED
    return (
        get_user_model()
        .objects.filter(
            Q(friendships_sent__to_user=user, friendships_sent__status=accepted)
            | Q(friendships_received__from_user=user, friendships_received__status=accepted)
        )
        .distinct()
        .order_by("first_name", "username")
    )


class BuddyGroup(models.Model):
    """A named list of friends, so a cheer can be sent to all of them at once."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="buddy_groups")
    name = models.CharField(max_length=100)
    members = models.ManyToManyField(User, related_name="in_buddy_groups", blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_group_name_per_owner")]
        ordering = ["name"]

    def __str__(self):
        return self.name


def _token():
    return secrets.token_urlsafe(24)


class Invitation(models.Model):
    """An invitation sent to someone who does not have an account yet."""

    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    message = models.TextField(blank=True)
    token = models.CharField(max_length=64, unique=True, default=_token)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["inviter", "email"], name="unique_invite_per_inviter")]

    def __str__(self):
        return f"{self.inviter} invited {self.email}"
