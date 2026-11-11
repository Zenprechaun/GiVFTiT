from django.core.management.base import BaseCommand

from gifting.services import expire_due


class Command(BaseCommand):
    help = "Close gifts that have passed their expiry date. Run daily (cron)."

    def handle(self, *args, **opts):
        self.stdout.write(f"{expire_due()} gifts expired")
