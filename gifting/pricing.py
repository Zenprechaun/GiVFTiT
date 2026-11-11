"""Price, tax and fee calculation for one unit of a product.

Rules carried over from the original application:
  * tax          = location tax rate x item price
  * cheering fee = CHEERING_FEE_RATE x item price
  * vendor fee   = VENDOR_FEE_RATE x item price
  * the vendor's fee level decides who pays each fee:
      Charitable         - the sender pays both
      Zero margin        - the sender pays the cheering fee, the vendor pays the vendor fee
      Maximum attraction - the vendor pays both
Fees paid by the sender are added to what the sender pays. Fees paid by the
vendor are taken out of what the vendor receives when the gift is redeemed.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from vendors.models import FeeLevel


def _portion(cents, rate):
    return int((Decimal(cents) * Decimal(rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class UnitPrice:
    price: int
    tax: int
    user_cheer_fee: int
    user_vendor_fee: int
    vendor_cheer_fee: int
    vendor_vendor_fee: int

    @property
    def value(self):
        return self.price + self.tax

    @property
    def user_fees(self):
        return self.user_cheer_fee + self.user_vendor_fee

    @property
    def sender_total(self):
        return self.value + self.user_fees

    @property
    def vendor_net(self):
        return self.value - self.vendor_cheer_fee - self.vendor_vendor_fee


def price_unit(price_cents, tax_rate_percent, fee_level):
    cheer_fee = _portion(price_cents, settings.CHEERING_FEE_RATE)
    vendor_fee = _portion(price_cents, settings.VENDOR_FEE_RATE)
    vendor_pays_cheer = fee_level == FeeLevel.MAX_ATTRACTION
    vendor_pays_vendor = fee_level in (FeeLevel.ZERO_MARGIN, FeeLevel.MAX_ATTRACTION)
    return UnitPrice(
        price=price_cents,
        tax=_portion(price_cents, Decimal(tax_rate_percent) / 100),
        user_cheer_fee=0 if vendor_pays_cheer else cheer_fee,
        user_vendor_fee=0 if vendor_pays_vendor else vendor_fee,
        vendor_cheer_fee=cheer_fee if vendor_pays_cheer else 0,
        vendor_vendor_fee=vendor_fee if vendor_pays_vendor else 0,
    )


def price_cart_item(item):
    return price_unit(item.product.price_cents, item.location.tax_rate, item.product.vendor.fee_level)
