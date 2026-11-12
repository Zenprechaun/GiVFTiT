# GiVFTiT

A social gifting platform: pick one or more items from local businesses, send them
to one or more friends as a **cheer**, and let each friend accept the gift or decline it.

This is a single Django application that replaces four older codebases
(ACheer2U, UAA, VBP, CCC). It was rewritten from their behavior, not ported from
their code.

## What's in it

| App | Replaces | What it does |
|---|---|---|
| `accounts` | UAA | Sign-up, login, profile, password reset (Django's built-in auth) |
| `social` | ACheer2U | Friends, buddy groups, email invitations |
| `vendors` | VBP | Businesses, locations, products, staff, the vendor portal, catalog integrations |
| `wallet` | CCC + UAA | Double-entry ledger, wallet balances, Stripe card payments |
| `gifting` | ACheer2U | Cart, checkout, the gift lifecycle, redemption codes, expiry |

The Django admin at `/admin/` is the back office: users, vendors, categories, and a
read-only view of every ledger entry.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_categories
python manage.py createsuperuser
python manage.py runserver
```

Open http://localhost:8000. With `PAYMENTS_PROVIDER=fake` (the default in `.env.example`)
card payments are simulated and nothing is charged. Emails print to the terminal.

Run the tests with `python manage.py test`.

### Or run it with Docker

```bash
docker compose up --build
```

Open http://localhost:8000. This starts the site and a PostgreSQL database, with
simulated payments. Create your admin login in a second terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

Stop with Ctrl+C. Your data is kept between runs; `docker compose down -v` erases it.

## How money works

All amounts are integer cents. Every movement of money is a balanced journal entry,
so balances are always recomputable from history and the admin shows a full audit trail.

For an item priced at $20.00 at a location with 10% tax and a "Charitable" vendor:

| Step | What happens |
|---|---|
| Purchase | Sender pays $25.00: $20.00 item + $2.00 tax + $2.00 cheering fee (10%) + $1.00 vendor fee (5%). $22.00 is held for the gift; $3.00 in fees is held as unearned. |
| Accept | The $3.00 in fees becomes platform revenue. The recipient gets a redemption code. |
| Redeem | Vendor staff enter the code. The vendor is owed $22.00. |
| Decline | The full $25.00 goes to the sender's wallet. |
| Expire | After `GIFT_EXPIRY_DAYS`, any gift not yet redeemed returns the full $25.00 to the sender's wallet. |

Each vendor picks a fee level that decides who pays the two fees:

- **Charitable** — the sender pays both.
- **Zero margin** — the sender pays the cheering fee; the vendor fee comes out of the vendor's share.
- **Maximum attraction** — both fees come out of the vendor's share.

Rates and the expiry period are settings (`CHEERING_FEE_RATE`, `VENDOR_FEE_RATE`, `GIFT_EXPIRY_DAYS`).

## Age-restricted categories

A category can carry a minimum age; alcohol is seeded at 21. For those items:

- the sender must have a date of birth on file showing they are old enough;
- registered recipients must too, and a recipient invited by email must add theirs before accepting (they can always decline);
- the redemption screen tells staff to check ID.

## Card payments (Stripe)

The site never handles card numbers. Customers pay on Stripe's hosted Checkout page and
Stripe confirms the payment through a signed webhook.

1. Set `PAYMENTS_PROVIDER=stripe`, `STRIPE_SECRET_KEY` and `SITE_URL`.
2. In the Stripe dashboard add a webhook endpoint at `https://<your-domain>/wallet/stripe/webhook/`
   for the events `checkout.session.completed` and `checkout.session.async_payment_succeeded`.
3. Put the endpoint's signing secret in `STRIPE_WEBHOOK_SECRET`.

Start with Stripe test-mode keys.

## Adding goods and services through integrations

Products come from *connectors*, not web scraping. A connector reads one external system
and yields products in a common shape; see `vendors/integrations/__init__.py`. A CSV
connector is included as a working example:

```bash
python manage.py sync_catalog <vendor-slug> --connector csv --option path=menu.csv
```

CSV columns: `external_id, name, price` and optionally `description, image_url, fulfilment`.
To add Square, Shopify, Toast or a gift-card network, subclass `CatalogConnector`.

## Deploying

Set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
`DATABASE_URL` (PostgreSQL) and real email settings. Then:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi
```

Serve `staticfiles/` from the web server, and run `python manage.py expire_gifts` daily.

## Not built yet

- **Vendor payouts.** The ledger tracks what each vendor is owed; paying it out (Stripe Connect) is not implemented.
- **Withdrawing a wallet balance to a bank account or card.**
- **Banking a gift's value** to the recipient's wallet (in the old app; removed for now), and **cannabis categories** (removed for now).
- **Wallet PIN, SMS notifications, social login, security questions** from the old apps.
- **Menus, regions, photos, reviews, fine-grained staff permissions, support tickets** from the old vendor portal. Staff roles are owner, manager and staff.
- **QR codes.** Gifts are redeemed with a typed 10-character code.
- **Delivery and shipment fulfilment.** Products can be labelled that way, but only in-person redemption exists.
- **Mobile app / API.**

## Decisions to confirm

These were chosen where the old code was ambiguous; each is a small change:

- A declined or expired gift refunds the sender's **wallet**, not their card, and includes the fees.
- An expired gift, even one already accepted, is refunded in full to the sender, not forfeited.
- A gift must be accepted by the recipient before staff can redeem it.
- Wallet top-ups are capped at $500 per transaction.
