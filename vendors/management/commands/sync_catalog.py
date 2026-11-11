from django.core.management.base import BaseCommand, CommandError

from vendors.integrations import CONNECTORS, sync_products
from vendors.models import Vendor


class Command(BaseCommand):
    help = "Sync a vendor's products from a catalog connector, e.g. --connector csv --option path=menu.csv"

    def add_arguments(self, parser):
        parser.add_argument("vendor", help="Vendor slug")
        parser.add_argument("--connector", required=True, choices=sorted(CONNECTORS))
        parser.add_argument("--option", action="append", default=[], help="key=value, repeatable")

    def handle(self, *args, **opts):
        try:
            vendor = Vendor.objects.get(slug=opts["vendor"])
        except Vendor.DoesNotExist:
            raise CommandError(f"No vendor with slug {opts['vendor']!r}")
        options = dict(item.split("=", 1) for item in opts["option"])
        connector = CONNECTORS[opts["connector"]](vendor, **options)
        created, updated, retired = sync_products(connector)
        self.stdout.write(f"{vendor}: {created} created, {updated} updated, {retired} retired")
