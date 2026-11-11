"""Import a vendor's catalog from a CSV file.

Columns: external_id, name, price (dollars), and optionally description,
image_url, fulfilment. This is the simplest working connector and the model
for API-based ones (Square, Shopify, Toast, ...).
"""
import csv
from decimal import Decimal

from . import CatalogConnector, ProductData, register


@register
class CsvConnector(CatalogConnector):
    name = "csv"

    def fetch_products(self):
        with open(self.options["path"], newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                yield ProductData(
                    external_id=row["external_id"].strip(),
                    name=row["name"].strip(),
                    price_cents=int((Decimal(row["price"]) * 100).to_integral_value()),
                    description=(row.get("description") or "").strip(),
                    image_url=(row.get("image_url") or "").strip(),
                    fulfilment=(row.get("fulfilment") or "in_person").strip(),
                )
