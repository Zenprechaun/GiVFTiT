from django.contrib import admin

from .models import BuddyGroup, Friendship, Invitation

admin.site.register(Friendship)
admin.site.register(BuddyGroup)
admin.site.register(Invitation)
