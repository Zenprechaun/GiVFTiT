from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import BuddyGroup, Friendship, Invitation, friends_of

User = get_user_model()


def _request_friend(request, identifier):
    identifier = identifier.strip()
    if not identifier:
        return
    other = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
    if other == request.user:
        messages.error(request, "That's you.")
        return
    if other:
        reverse_request = Friendship.objects.filter(from_user=other, to_user=request.user).first()
        if reverse_request:
            reverse_request.status = Friendship.Status.ACCEPTED
            reverse_request.save(update_fields=["status"])
            messages.success(request, f"You and {other.display_name} are now friends.")
            return
        _, created = Friendship.objects.get_or_create(from_user=request.user, to_user=other)
        messages.success(request, "Friend request sent." if created else "You already sent that request.")
        return
    try:
        validate_email(identifier)
    except ValidationError:
        messages.error(request, "No member with that username. Enter an email address to invite them.")
        return
    invitation, created = Invitation.objects.get_or_create(inviter=request.user, email=identifier.lower())
    if created:
        link = f"{settings.SITE_URL}{reverse('accounts:signup')}?email={invitation.email}"
        send_mail(
            f"{request.user.display_name} invited you to {settings.SITE_NAME}",
            f"{request.user.display_name} wants to send you gifts on {settings.SITE_NAME}.\n\nJoin here: {link}\n",
            settings.DEFAULT_FROM_EMAIL,
            [invitation.email],
        )
    messages.success(request, f"Invitation sent to {invitation.email}.")


@login_required
def friends(request):
    if request.method == "POST":
        _request_friend(request, request.POST.get("identifier", ""))
        return redirect("social:friends")
    context = {
        "friends": friends_of(request.user),
        "incoming": Friendship.objects.filter(
            to_user=request.user, status=Friendship.Status.PENDING
        ).select_related("from_user"),
        "outgoing": Friendship.objects.filter(
            from_user=request.user, status=Friendship.Status.PENDING
        ).select_related("to_user"),
        "invitations": Invitation.objects.filter(inviter=request.user, accepted_at__isnull=True),
        "groups": BuddyGroup.objects.filter(owner=request.user).prefetch_related("members"),
    }
    return render(request, "social/friends.html", context)


@login_required
@require_POST
def respond(request, pk, action):
    friendship = get_object_or_404(
        Friendship, pk=pk, to_user=request.user, status=Friendship.Status.PENDING
    )
    friendship.status = (
        Friendship.Status.ACCEPTED if action == "accept" else Friendship.Status.DECLINED
    )
    friendship.save(update_fields=["status"])
    return redirect("social:friends")


@login_required
@require_POST
def group_create(request):
    name = request.POST.get("name", "").strip()
    if name:
        group, _ = BuddyGroup.objects.get_or_create(owner=request.user, name=name[:100])
        return redirect("social:group", pk=group.pk)
    return redirect("social:friends")


@login_required
def group(request, pk):
    group = get_object_or_404(BuddyGroup, pk=pk, owner=request.user)
    my_friends = friends_of(request.user)
    if request.method == "POST":
        if "delete" in request.POST:
            group.delete()
            return redirect("social:friends")
        # Only accepted friends can be put in a group.
        chosen = my_friends.filter(pk__in=request.POST.getlist("members"))
        group.members.set(chosen)
        messages.success(request, "Group updated.")
        return redirect("social:group", pk=group.pk)
    member_ids = set(group.members.values_list("pk", flat=True))
    return render(
        request, "social/group.html", {"group": group, "friends": my_friends, "member_ids": member_ids}
    )
