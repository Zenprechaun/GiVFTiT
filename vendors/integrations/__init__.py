"""Catalog integrations.

Vendors' goods and services come from *connectors* rather than web scraping.
A connector knows how to read one external system (a point-of-sale, an
e-commerce store, a gift-card network, a spreadsheet) and yields products in a
common shape. ``sync_products`` then creates, updates and retires products.

To add an integration, subclass ``CatalogConnector`` in a new module, decorate
it with ``@register`` and import the module at the bottom of this file.
"""
from dataclasses import dataclass

from django.db import transaction

from ..models import Product


@dataclass(frozen=True)
class ProductData:
    external_id: str
    name: str
    price_cents: int
    description: str = ""
    image_url: str = ""
    fulfilment: str = Product.Fulfilment.IN_PERSON


class CatalogConnector:
    """Base class for a catalog source."""

    name = ""

    def __init__(self, vendor, **options):
        self.vendor = vendor
        self.options = options

    def fetch_products(self):
        """Yield ``ProductData`` for every product currently offered."""
        raise NotImplementedError


CONNECTORS = {}


def register(cls):
    CONNECTORS[cls.name] = cls
    return cls


@transaction.atomic
def sync_products(connector):
    """Bring the vendor's products from this connector in line with the source.

    Returns (created, updated, retired). Products that disappear from the
    source are deactivated, never deleted, so past gifts keep their history.
    """
    vendor, source = connector.vendor, connector.name
    seen, created, updated = set(), 0, 0
    for item in connector.fetch_products():
        seen.add(item.external_id)
        _, was_created = Product.objects.update_or_create(
            vendor=vendor,
            source=source,
            external_id=item.external_id,
            defaults={
                "name": item.name[:200],
                "description": item.description,
                "price_cents": item.price_cents,
                "image_url": item.image_url,
                "fulfilment": item.fulfilment,
                "is_active": True,
            },
        )
        created += was_created
        updated += not was_created
    retired = (
        Product.objects.filter(vendor=vendor, source=source, is_active=True)
        .exclude(external_id__in=seen)
        .update(is_active=False)
    )
    return created, updated, retired


from . import csv_connector  # noqa: E402,F401  (registers the connector)
