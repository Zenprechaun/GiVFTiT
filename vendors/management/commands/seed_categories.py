from django.core.management.base import BaseCommand

from vendors.models import Category

# (name, minimum age). Alcohol is restricted to 21+.
CATEGORIES = [
    ("Restaurants", 0),
    ("Bars & Spirits", 21),
    ("Coffee & Bakery", 0),
    ("Retail", 0),
    ("Health & Beauty", 0),
    ("Entertainment", 0),
    ("Services", 0),
]


class Command(BaseCommand):
    help = "Create the starting set of business categories."

    def handle(self, *args, **opts):
        from django.utils.text import slugify

        for name, age in CATEGORIES:
            Category.objects.update_or_create(
                slug=slugify(name), defaults={"name": name, "minimum_age": age}
            )
        self.stdout.write(f"{len(CATEGORIES)} categories ready")
