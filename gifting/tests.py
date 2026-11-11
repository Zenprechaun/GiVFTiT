from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from social.models import Friendship, Invitation, friends_of
from vendors.models import Category, FeeLevel, Location, Product, StaffMember, Vendor
from wallet.models import Account, JournalEntry, Payment, Posting
from wallet.payments import mark_paid, start_payment
from wallet.services import InsufficientFunds, cr, dr, payable_for, post, system_account, wallet_for

from . import services
from .models import CartItem, Cheer, Gift
from .pricing import price_unit

User = get_user_model()


def make_user(name, **extra):
    return User.objects.create_user(name, f"{name}@example.com", "pw-for-tests-123", **extra)


def fund(user, cents):
    post("test funding", [dr(system_account(Account.Kind.PROCESSOR_CLEARING), cents), cr(wallet_for(user), cents)])


def balance(kind):
    return system_account(kind).balance()


class PricingTests(TestCase):
    def test_charitable_sender_pays_both_fees(self):
        unit = price_unit(1000, Decimal("7.25"), FeeLevel.CHARITABLE)
        self.assertEqual((unit.tax, unit.user_cheer_fee, unit.user_vendor_fee), (73, 100, 50))
        self.assertEqual(unit.sender_total, 1223)
        self.assertEqual(unit.vendor_net, 1073)

    def test_zero_margin_vendor_pays_vendor_fee(self):
        unit = price_unit(1000, 0, FeeLevel.ZERO_MARGIN)
        self.assertEqual(unit.sender_total, 1100)
        self.assertEqual(unit.vendor_net, 950)

    def test_max_attraction_vendor_pays_both(self):
        unit = price_unit(1000, 0, FeeLevel.MAX_ATTRACTION)
        self.assertEqual(unit.sender_total, 1000)
        self.assertEqual(unit.vendor_net, 850)


class LedgerTests(TestCase):
    def test_unbalanced_entry_is_rejected(self):
        user = make_user("a")
        with self.assertRaises(ValueError):
            post("bad", [dr(system_account(Account.Kind.PROCESSOR_CLEARING), 100), cr(wallet_for(user), 90)])

    def test_wallet_cannot_go_negative(self):
        user = make_user("a")
        fund(user, 500)
        with self.assertRaises(InsufficientFunds):
            post("overspend", [dr(wallet_for(user), 501), cr(system_account(Account.Kind.GIFT_ESCROW), 501)])
        self.assertEqual(wallet_for(user).balance(), 500)

    def test_idempotency_key_prevents_double_posting(self):
        user = make_user("a")
        lines = [dr(system_account(Account.Kind.PROCESSOR_CLEARING), 100), cr(wallet_for(user), 100)]
        post("once", lines, idempotency_key="k")
        post("once", lines, idempotency_key="k")
        self.assertEqual(wallet_for(user).balance(), 100)

    def test_topup_payment_is_credited_once(self):
        user = make_user("a")
        payment, url = start_payment(user, Payment.Purpose.TOPUP, 2500, "top-up")
        self.assertIn(str(payment.pk), url)
        mark_paid(payment.pk)
        mark_paid(payment.pk)
        self.assertEqual(wallet_for(user).balance(), 2500)


class GiftFlowBase(TestCase):
    fee_level = FeeLevel.CHARITABLE

    def setUp(self):
        self.sender = make_user("sender", date_of_birth=date(1980, 1, 1))
        self.friend = make_user("friend", date_of_birth=date(1985, 1, 1))
        self.owner = make_user("owner")
        self.category = Category.objects.create(name="Restaurants", slug="restaurants")
        self.vendor = Vendor.objects.create(name="Cafe", category=self.category, fee_level=self.fee_level)
        self.location = Location.objects.create(vendor=self.vendor, name="Main", tax_rate=Decimal("10"))
        self.product = Product.objects.create(vendor=self.vendor, name="Lunch", price_cents=2000)
        StaffMember.objects.create(vendor=self.vendor, user=self.owner, role=StaffMember.Role.OWNER)

    def send(self, recipients=None, emails=(), method=Cheer.Method.WALLET, quantity=1):
        CartItem.objects.create(user=self.sender, product=self.product, location=self.location, quantity=quantity)
        recipients = [self.friend] if recipients is None else recipients
        return services.create_cheer(self.sender, recipients, list(emails), "Enjoy!", method)

    def assert_books_balance(self):
        self.assertEqual(sum(Posting.objects.values_list("amount", flat=True)), 0)


class GiftLifecycleTests(GiftFlowBase):
    # Lunch: price 2000, tax 200, cheering fee 200, vendor fee 100 -> sender pays 2500.

    def test_wallet_purchase_holds_value_and_fees(self):
        fund(self.sender, 3000)
        cheer, url = self.send()
        self.assertIsNone(url)
        self.assertEqual(cheer.status, Cheer.Status.PAID)
        self.assertEqual(cheer.total_cents, 2500)
        self.assertEqual(wallet_for(self.sender).balance(), 500)
        self.assertEqual(balance(Account.Kind.GIFT_ESCROW), 2200)
        self.assertEqual(balance(Account.Kind.UNEARNED_FEES), 300)
        self.assertFalse(CartItem.objects.exists())
        self.assert_books_balance()

    def test_insufficient_wallet_rolls_everything_back(self):
        fund(self.sender, 100)
        with self.assertRaises(InsufficientFunds):
            self.send()
        self.assertFalse(Cheer.objects.exists())
        self.assertEqual(wallet_for(self.sender).balance(), 100)

    def test_accept_then_redeem_pays_vendor(self):
        fund(self.sender, 2500)
        cheer, _ = self.send()
        gift = cheer.gifts.get()
        services.accept(gift.pk, self.friend)
        self.assertEqual(balance(Account.Kind.FEE_REVENUE), 300)
        services.redeem(gift.pk, self.owner)
        gift.refresh_from_db()
        self.assertEqual(gift.status, Gift.Status.REDEEMED)
        self.assertEqual(payable_for(self.vendor).balance(), 2200)
        self.assertEqual(balance(Account.Kind.GIFT_ESCROW), 0)
        self.assertEqual(balance(Account.Kind.UNEARNED_FEES), 0)
        self.assert_books_balance()

    def test_gift_cannot_be_redeemed_twice_or_by_outsiders(self):
        fund(self.sender, 2500)
        gift = self.send()[0].gifts.get()
        with self.assertRaises(services.GiftingError):
            services.redeem(gift.pk, self.owner)  # not accepted yet
        services.accept(gift.pk, self.friend)
        with self.assertRaises(services.GiftingError):
            services.redeem(gift.pk, self.friend)  # not on the vendor's staff
        services.redeem(gift.pk, self.owner)
        with self.assertRaises(services.GiftingError):
            services.redeem(gift.pk, self.owner)
        self.assertEqual(payable_for(self.vendor).balance(), 2200)

    def test_deny_returns_everything_to_sender(self):
        fund(self.sender, 2500)
        gift = self.send()[0].gifts.get()
        services.deny(gift.pk, self.friend)
        self.assertEqual(wallet_for(self.sender).balance(), 2500)
        self.assertEqual(balance(Account.Kind.GIFT_ESCROW), 0)
        self.assertEqual(balance(Account.Kind.FEE_REVENUE), 0)
        self.assert_books_balance()

    def test_only_the_recipient_can_respond(self):
        fund(self.sender, 2500)
        gift = self.send()[0].gifts.get()
        for action in (services.accept, services.deny):
            with self.assertRaises(services.GiftingError):
                action(gift.pk, self.sender)

    def test_many_recipients_and_quantities(self):
        other = make_user("other")
        fund(self.sender, 10000)
        cheer, _ = self.send(recipients=[self.friend, other], quantity=2)
        self.assertEqual(cheer.gifts.count(), 4)
        self.assertEqual(cheer.total_cents, 10000)
        self.assertEqual(len(set(cheer.gifts.values_list("code", flat=True))), 4)

    def test_card_purchase_completes_when_payment_clears(self):
        cheer, url = self.send(method=Cheer.Method.CARD)
        self.assertTrue(url)
        self.assertEqual(cheer.status, Cheer.Status.AWAITING_PAYMENT)
        self.assertEqual(JournalEntry.objects.count(), 0)
        mark_paid(cheer.payment_id)
        mark_paid(cheer.payment_id)  # a repeated webhook must not double-post
        cheer.refresh_from_db()
        self.assertEqual(cheer.status, Cheer.Status.PAID)
        self.assertEqual(balance(Account.Kind.PROCESSOR_CLEARING), 2500)
        self.assertEqual(balance(Account.Kind.GIFT_ESCROW), 2200)
        self.assert_books_balance()

    def test_email_recipient_claims_gift_on_signup_and_befriends_inviter(self):
        fund(self.sender, 2500)
        Invitation.objects.create(inviter=self.sender, email="new@example.com")
        gift = self.send(recipients=[], emails=["New@Example.com"])[0].gifts.get()
        self.assertIsNone(gift.recipient)
        newcomer = User.objects.create_user("new", "new@example.com", "pw-for-tests-123")
        gift.refresh_from_db()
        self.assertEqual(gift.recipient, newcomer)
        self.assertIn(self.sender, friends_of(newcomer))

    def test_expiry_returns_unredeemed_gifts_to_the_sender_in_full(self):
        fund(self.sender, 5000)
        pending, accepted = self.send(quantity=2)[0].gifts.all()
        services.accept(accepted.pk, self.friend)
        self.assertEqual(services.expire_due(), 0)
        self.assertEqual(services.expire_due(now=timezone.now() + timedelta(days=400)), 2)
        self.assertEqual(wallet_for(self.sender).balance(), 5000)
        self.assertEqual(wallet_for(self.friend).balance(), 0)
        self.assertEqual(balance(Account.Kind.FEE_REVENUE), 0)
        self.assertEqual(balance(Account.Kind.GIFT_ESCROW), 0)
        self.assert_books_balance()


class VendorPaidFeeTests(GiftFlowBase):
    fee_level = FeeLevel.MAX_ATTRACTION

    def test_vendor_paid_fees_come_out_of_the_vendor_share(self):
        fund(self.sender, 2200)
        cheer, _ = self.send()
        self.assertEqual(cheer.total_cents, 2200)
        gift = cheer.gifts.get()
        services.accept(gift.pk, self.friend)
        services.redeem(gift.pk, self.owner)
        self.assertEqual(payable_for(self.vendor).balance(), 1900)
        self.assertEqual(balance(Account.Kind.FEE_REVENUE), 300)
        self.assert_books_balance()


class AgeRestrictionTests(GiftFlowBase):
    def setUp(self):
        super().setUp()
        self.category.minimum_age = 21
        self.category.save()
        fund(self.sender, 10000)

    def test_adults_can_send_and_accept(self):
        gift = self.send()[0].gifts.get()
        self.assertEqual(gift.minimum_age, 21)
        services.accept(gift.pk, self.friend)

    def test_sender_without_date_of_birth_is_blocked(self):
        self.sender.date_of_birth = None
        self.sender.save()
        with self.assertRaises(services.GiftingError):
            self.send()

    def test_underage_recipient_is_blocked(self):
        self.friend.date_of_birth = date.today() - timedelta(days=365 * 19)
        self.friend.save()
        with self.assertRaises(services.GiftingError):
            self.send()

    def test_email_recipient_must_prove_age_to_accept_but_can_decline(self):
        gift = self.send(recipients=[], emails=["kid@example.com"])[0].gifts.get()
        kid = User.objects.create_user("kid", "kid@example.com", "pw-for-tests-123")
        with self.assertRaises(services.GiftingError):
            services.accept(gift.pk, kid)
        services.deny(gift.pk, kid)


@override_settings(PAYMENTS_PROVIDER="fake")
class WebFlowTests(GiftFlowBase):
    """Click through the whole site the way a browser would."""

    def test_end_to_end(self):
        Friendship.objects.create(from_user=self.sender, to_user=self.friend, status=Friendship.Status.ACCEPTED)
        c = self.client
        self.assertContains(c.get(reverse("home")), "Cafe")
        self.assertContains(c.get(reverse("vendors:detail", args=[self.vendor.slug])), "Lunch")

        c.force_login(self.sender)
        c.post(reverse("gifting:cart_add"), {"product": self.product.pk, "location": self.location.pk, "quantity": 1})
        self.assertContains(c.get(reverse("gifting:cart")), "$25.00")
        self.assertContains(c.get(reverse("gifting:checkout")), "friend")
        response = c.post(reverse("gifting:checkout"), {"friends": [self.friend.pk], "message": "Hi", "method": "card"})
        payment = Payment.objects.get()
        self.assertRedirects(response, reverse("wallet:fake_pay", args=[payment.pk]))
        c.post(reverse("wallet:fake_pay", args=[payment.pk]), {"pay": "1"})
        self.assertContains(c.get(reverse("wallet:payment_done", args=[payment.pk])), "Payment received")
        self.assertContains(c.get(reverse("gifting:cheers")), "Lunch")
        for name in ("social:friends", "wallet:wallet", "accounts:profile"):
            self.assertEqual(c.get(reverse(name)).status_code, 200)

        gift = Gift.objects.get()
        c.force_login(self.friend)
        self.assertContains(c.get(reverse("gifting:cheers")), "Accept")
        c.post(reverse("gifting:gift_action", args=[gift.pk, "accept"]))
        self.assertContains(c.get(reverse("gifting:gift", args=[gift.pk])), gift.display_code)

        c.force_login(self.owner)
        self.assertContains(c.get(reverse("portal:redeem"), {"code": gift.display_code}), "Confirm and redeem")
        c.post(reverse("portal:redeem"), {"code": gift.code, "confirm": "1"})
        gift.refresh_from_db()
        self.assertEqual(gift.status, Gift.Status.REDEEMED)
        self.assertContains(c.get(reverse("portal:dashboard")), "$22.00")
        for name in ("portal:products", "portal:locations", "portal:product_new", "portal:location_new"):
            self.assertEqual(c.get(reverse(name)).status_code, 200)

    def test_new_business_signup_and_product(self):
        user = make_user("newbiz")
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("portal:dashboard")), reverse("portal:join"))
        self.client.post(reverse("portal:join"), {
            "name": "Bike Shop", "category": self.category.pk, "fee_level": "charitable",
            "location_name": "Main", "tax_rate": "8.5",
        })
        vendor = Vendor.objects.get(name="Bike Shop")
        self.client.post(reverse("portal:product_new"), {"name": "Tune-up", "price": "49.99", "fulfilment": "in_person", "is_active": "on"})
        self.assertEqual(vendor.products.get().price_cents, 4999)

    def test_signup_page_creates_account(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "zoe", "email": "zoe@example.com", "first_name": "Zoe", "last_name": "Q",
            "password1": "a-long-test-passphrase-9", "password2": "a-long-test-passphrase-9",
        })
        self.assertRedirects(response, reverse("home"))

    def test_pages_require_login_and_other_peoples_payments_are_hidden(self):
        self.assertEqual(self.client.get(reverse("gifting:cart")).status_code, 302)
        payment, _ = start_payment(self.sender, Payment.Purpose.TOPUP, 1000, "x")
        self.client.force_login(self.friend)
        self.assertEqual(self.client.get(reverse("wallet:fake_pay", args=[payment.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("wallet:stripe_webhook"), b"{}", content_type="application/json").status_code, 400)


@override_settings(PAYMENTS_PROVIDER="stripe", STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookTests(GiftFlowBase):
    def deliver(self, payment, amount, secret="whsec_test"):
        import hashlib, hmac, json, time

        payload = json.dumps({
            "id": "evt_1", "object": "event", "type": "checkout.session.completed",
            "data": {"object": {
                "id": payment.provider_ref, "object": "checkout.session", "payment_status": "paid",
                "client_reference_id": str(payment.pk), "amount_total": amount,
            }},
        })
        stamp = int(time.time())
        signature = hmac.new(secret.encode(), f"{stamp}.{payload}".encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            reverse("wallet:stripe_webhook"), payload, content_type="application/json",
            headers={"Stripe-Signature": f"t={stamp},v1={signature}"},
        )

    def make_payment(self):
        return Payment.objects.create(
            user=self.sender, purpose=Payment.Purpose.TOPUP, amount_cents=1500, provider="stripe", provider_ref="cs_test_1"
        )

    def test_signed_webhook_credits_wallet_once(self):
        payment = self.make_payment()
        self.assertEqual(self.deliver(payment, 1500).status_code, 200)
        self.assertEqual(self.deliver(payment, 1500).status_code, 200)
        self.assertEqual(wallet_for(self.sender).balance(), 1500)

    def test_forged_signature_and_wrong_amount_are_ignored(self):
        payment = self.make_payment()
        self.assertEqual(self.deliver(payment, 1500, secret="whsec_wrong").status_code, 400)
        self.assertEqual(self.deliver(payment, 1).status_code, 200)
        self.assertEqual(wallet_for(self.sender).balance(), 0)
