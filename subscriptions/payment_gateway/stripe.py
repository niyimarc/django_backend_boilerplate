import stripe
from django.utils import timezone
from decimal import Decimal
from subscriptions.models import Subscription, SubscriptionStatus, PaymentProvider, StripeEventLog
from subscriptions.utils import get_subscription_setting
# Backward & forward compatible error alias
try:
    from stripe import error as stripe_error  # For Stripe <11.x
except ImportError:
    stripe_error = stripe  # For Stripe >=11.x

INTERVAL_MAP = {
    "daily": "day",
    "day": "day",
    "weekly": "week",
    "week": "week",
    "monthly": "month",
    "month": "month",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
}


def configure(keys: dict):
    """
    Inject Stripe API credentials dynamically.
    Called automatically by the payment router.
    """
    stripe.api_key = keys.get("secret_key")
    # print(f"[Stripe] Configured with secret key: {'****' if stripe.api_key else 'MISSING'}")

def create_checkout_session(user, plan, success_url, cancel_url):
    """
    Create a Stripe Checkout Session for a subscription plan.
    """
    price = plan.get_price()
    if not price:
        raise ValueError("No price found for this plan.")

    customer = _get_or_create_customer(user)
    amount = int(Decimal(price.amount) * 100)

    interval_map = {
        "monthly": "month",
        "yearly": "year",
        "weekly": "week",
        "daily": "day",
    }
    interval = interval_map.get(plan.interval.lower(), "month")

    session = stripe.checkout.Session.create(
        customer=customer.id,
        payment_method_types=["card"],
        mode="subscription",
        payment_method_collection="if_required",  # Only ask for card if price > 0
        line_items=[
            {
                "price_data": {
                    "currency": price.currency.lower(),
                    "unit_amount": amount,
                    "product_data": {
                        "name": plan.name,
                        "metadata": {"plan_slug": plan.slug},
                    },
                    "recurring": {"interval": interval},
                },
                "quantity": 1,
            }
        ],
        metadata={
            "plan_slug": plan.slug,
            "user_id": str(user.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return session

def _get_or_create_customer(user):
    """Ensure a Stripe Customer exists and is linked to the user's profile."""
    from user_profile.models import Profile

    profile, _ = Profile.objects.get_or_create(user=user)

    if profile.stripe_customer_id:
        try:
            customer = stripe.Customer.retrieve(profile.stripe_customer_id)
            if not customer.get("deleted", False):
                return customer
        except stripe_error.InvalidRequestError:
            profile.stripe_customer_id = None
            profile.save(update_fields=["stripe_customer_id"])

    # Create new
    customer = stripe.Customer.create(
        email=user.email,
        name=user.get_full_name() or user.username,
        metadata={"user_id": user.id},
    )
    profile.stripe_customer_id = customer.id
    profile.save(update_fields=["stripe_customer_id"])
    # print(f"[Stripe] New customer created: {customer.id}")

    return customer

def handle_webhook(event):
    from subscriptions.models import StripeEventLog

    StripeEventLog.objects.create(event_type=event["type"], data=event)
    data = event["data"]["object"]
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        _on_checkout_completed(data)
    elif event_type == "invoice.payment_succeeded":
        _on_payment_success(data)
    elif event_type == "customer.subscription.deleted":
        _on_subscription_canceled(data)

def _on_checkout_completed(data):
    """Triggered after successful checkout."""
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    if not (customer_id and subscription_id):
        # print(f"[Stripe] Missing customer/subscription info in checkout.session.completed")
        return

    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(profile__stripe_customer_id=customer_id).first()
    if not user:
        # print(f"[Stripe] No user found for customer {customer_id}")
        return

    try:
        sub_data = stripe.Subscription.retrieve(subscription_id, expand=["items.data.price.product"])
    except Exception as e:
        # print(f"[Stripe] Error retrieving subscription: {e}")
        return

    # Identify plan
    plan_slug = (
        data.get("metadata", {}).get("plan_slug")
        or sub_data.get("metadata", {}).get("plan_slug")
        or sub_data["items"]["data"][0]["price"]["product"].get("metadata", {}).get("plan_slug")
    )

    from subscriptions.models import Plan
    plan = None
    if plan_slug:
        plan = Plan.objects.filter(slug=plan_slug).first()
    if not plan:
        interval = sub_data["items"]["data"][0]["price"]["recurring"]["interval"]
        plan = Plan.objects.filter(interval__icontains=interval).first()
    if not plan:
        # print(f"[Stripe] Could not determine plan for subscription {subscription_id}")
        return

    # Handle period safely
    current_start_ts = getattr(sub_data, "current_period_start", None)
    current_end_ts = getattr(sub_data, "current_period_end", None)

    if not current_start_ts or not current_end_ts:
        from subscriptions.conf import get_period_func
        period_func = get_period_func()
        current_period_start = timezone.now()
        current_period_end = period_func(plan.interval, current_period_start)
    else:
        current_period_start = timezone.make_aware(
            timezone.datetime.fromtimestamp(current_start_ts)
        )
        current_period_end = timezone.make_aware(
            timezone.datetime.fromtimestamp(current_end_ts)
        )

    price_data = sub_data["items"]["data"][0]["price"]
    currency = price_data["currency"].upper()
    amount = Decimal(price_data["unit_amount"]) / 100

    # Cancel existing active subscriptions for this user
    active_subs = Subscription.objects.filter(
        user=user,
        status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
    )

    for sub in active_subs:
        sub.status = SubscriptionStatus.CANCELED
        sub.cancel_at_period_end = True
        sub.save(update_fields=["status", "cancel_at_period_end"])

    # Always create a *new* subscription record for each checkout
    new_subscription = Subscription.objects.create(
        user=user,
        plan=plan,
        status=sub_data["status"].lower(),
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        currency=currency,
        unit_amount=amount,
        provider=PaymentProvider.STRIPE,
        external_customer_id=customer_id,
        external_subscription_id=subscription_id,
    )

    # print(f"[Stripe] Created new subscription {new_subscription.id} for {user.username} → {plan.slug}")


def _on_payment_success(data):
    customer_id = data.get("customer")
    sub_id = data.get("subscription")
    if not sub_id or not customer_id:
        return

    try:
        sub_data = stripe.Subscription.retrieve(sub_id)
        current_end = timezone.make_aware(
            timezone.datetime.fromtimestamp(sub_data["current_period_end"])
        )

        # Only update the active subscription matching this sub_id
        Subscription.objects.filter(
            external_subscription_id=sub_id,
            external_customer_id=customer_id,
        ).update(current_period_end=current_end)

        # print(f"[Stripe] Payment success synced for subscription {sub_id}")

    except Exception as e:
        print(f"[Stripe] Payment success handler failed: {e}")

def _on_subscription_canceled(data):
    sub_id = data.get("id")
    if not sub_id:
        return

    try:
        affected = Subscription.objects.filter(external_subscription_id=sub_id).update(
            status=SubscriptionStatus.CANCELED,
            cancel_at_period_end=True,
        )

        # if affected:
        #     print(f"[Stripe] Subscription {sub_id} marked as canceled.")
        # else:
        #     print(f"[Stripe] Cancel webhook for unknown subscription {sub_id}")

    except Exception as e:
        print(f"[Stripe] Cancel webhook failed: {e}")

def process_upgrade(subscription, new_plan, prorate=None):
    from subscriptions.payment_gateway.sync_stripe import ensure_product_for_plan

    settings = get_subscription_setting()
    prorate = settings.prorate_on_upgrade if prorate is None else prorate
    effect = settings.upgrade_effect
    refund_policy = settings.refund_policy

    # print(f"[Stripe] Upgrading {subscription.id} → {new_plan.slug} | effect={effect}, prorate={prorate}, refund={refund_policy}")

    product_id = new_plan.stripe_product_id or ensure_product_for_plan(new_plan)
    sub = stripe.Subscription.retrieve(subscription.external_subscription_id)
    current_item = sub["items"]["data"][0]

    price_obj = new_plan.get_price()
    price = stripe.Price.create(
        unit_amount=int(price_obj.amount * 100),
        currency=price_obj.currency.lower(),
        recurring={"interval": INTERVAL_MAP.get(new_plan.interval.lower(), "month")},
        product=product_id,  # use correct plan product
    )

    # print(f"[Stripe] Created temporary price {price.id} for {new_plan.slug}")

    stripe.Subscription.modify(
        subscription.external_subscription_id,
        cancel_at_period_end=False,
        proration_behavior="create_prorations" if prorate else "none",
        items=[{
            "id": current_item.id,
            "price": price.id,
        }],
    )

    # print(f"[Stripe] Upgrade applied on Stripe → {new_plan.slug}")

    # Update Django
    subscription.plan = new_plan
    subscription.unit_amount = price_obj.amount
    subscription.currency = price_obj.currency
    subscription.updated_at = timezone.now()
    subscription.save(update_fields=["plan", "unit_amount", "currency", "updated_at"])
    # print(f"[DB] Updated local subscription {subscription.id} → {new_plan.slug}")

    # Optional refund
    if refund_policy in ("partial", "full"):
        _handle_refund(subscription, refund_policy)

def process_downgrade(subscription, new_plan, refund_policy=None):
    """
    Downgrade an active Stripe subscription to a lower-tier plan.
    Uses plan.stripe_product_id if available.
    Honors refund policy, downgrade effect, and proration setting from admin.
    Updates both Stripe and the local Subscription model.
    """
    from subscriptions.payment_gateway.sync_stripe import ensure_product_for_plan
    from subscriptions.payment_gateway.stripe import sync_subscription_status  # optional

    settings = get_subscription_setting()
    refund_policy = refund_policy or settings.refund_policy
    effect = settings.downgrade_effect  # "immediate" or "end_of_period"
    prorate = settings.prorate_on_downgrade

    # print(
    #     f"[Stripe] Downgrading {subscription.id} → {new_plan.slug} | "
    #     f"effect={effect}, prorate={prorate}, refund={refund_policy}"
    # )

    # Ensure the product exists for this plan
    product_id = new_plan.stripe_product_id or ensure_product_for_plan(new_plan)

    # Retrieve the current Stripe subscription
    sub = stripe.Subscription.retrieve(subscription.external_subscription_id)
    current_item = sub["items"]["data"][0]

    # Create a temporary Stripe Price for the downgrade
    price_obj = new_plan.get_price()
    price = stripe.Price.create(
        unit_amount=int(price_obj.amount * 100),
        currency=price_obj.currency.lower(),
        recurring={"interval": INTERVAL_MAP.get(new_plan.interval.lower(), "month")},
        product=product_id,
    )

    # print(f"[Stripe] Created temporary price {price.id} for downgrade to {new_plan.slug}")

    # Apply downgrade behavior
    if effect == "immediate":
        stripe.Subscription.modify(
            subscription.external_subscription_id,
            cancel_at_period_end=False,
            proration_behavior="create_prorations" if prorate else "none",
            items=[{
                "id": current_item.id,
                "price": price.id,
            }],
        )
        # print("[Stripe] Immediate downgrade applied.")
    else:
        stripe.Subscription.modify(
            subscription.external_subscription_id,
            cancel_at_period_end=True,
        )
        # print("[Stripe] Downgrade scheduled for next billing period.")

    # Update local Django subscription
    subscription.plan = new_plan
    subscription.unit_amount = price_obj.amount
    subscription.currency = price_obj.currency
    subscription.updated_at = timezone.now()

    # If it's a scheduled downgrade, we keep current plan active until renewal
    if effect == "immediate":
        subscription.status = SubscriptionStatus.ACTIVE
    else:
        subscription.cancel_at_period_end = True

    subscription.save(update_fields=[
        "plan", "unit_amount", "currency", "updated_at", "status", "cancel_at_period_end"
    ])

    # print(f"[DB] Updated local subscription {subscription.id} → {new_plan.slug}")

    # Handle refund if policy allows
    if refund_policy in ("partial", "full"):
        _handle_refund(subscription, refund_policy)

    # (Optional) Resync with Stripe to confirm remote status
    try:
        sync_subscription_status(subscription)
    except Exception as e:
        print(f"[Stripe] Optional post-sync failed: {e}")


def process_cancellation(subscription, cancel_effect, refund_policy):
    """Cancels or schedules cancellation on Stripe."""
    try:
        # First, sync to ensure local state is current
        sync_subscription_status(subscription)

        sub_data = stripe.Subscription.retrieve(subscription.external_subscription_id)

        if sub_data.status in ["canceled", "incomplete_expired"]:
            # print(f"[Stripe] Subscription {subscription.id} already inactive remotely.")
            return

        if cancel_effect == "immediate":
            stripe.Subscription.delete(subscription.external_subscription_id)
        else:
            stripe.Subscription.modify(
                subscription.external_subscription_id,
                cancel_at_period_end=True,
            )

        subscription.status = "canceled"
        subscription.cancel_at_period_end = cancel_effect == "end_of_period"
        subscription.save(update_fields=["status", "cancel_at_period_end"])

        if refund_policy in ["partial", "full"]:
            _handle_refund(subscription, refund_policy)

        # print(f"[Stripe] Subscription {subscription.id} cancelled ({cancel_effect}).")

    except Exception as e:
        print(f"[Stripe] Cancellation error for {subscription.id}: {e}")


def _handle_refund(subscription, refund_policy):
    """
    Handles refunds according to the global refund policy.

    refund_policy can be:
      - "none": No refund
      - "partial": Refunds prorated for unused time
      - "full": Refunds full last payment amount
    """
    if refund_policy == "none":
        # print(f"[Stripe] Refund policy set to 'none' — no refund processed.")
        return

    try:
        # Retrieve the latest invoice/payment intent associated with the subscription
        invoices = stripe.Invoice.list(subscription=subscription.external_subscription_id, limit=1)
        if not invoices.data:
            # print(f"[Stripe] No invoices found for subscription {subscription.id}. Cannot issue refund.")
            return

        invoice = invoices.data[0]
        payment_intent_id = invoice.get("payment_intent")
        if not payment_intent_id:
            # print(f"[Stripe] No payment intent found on invoice {invoice.id}.")
            return

        # Get payment intent details
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        charge_id = payment_intent["charges"]["data"][0]["id"]

        if refund_policy == "full":
            refund = stripe.Refund.create(charge=charge_id)
            refund_reason = "Full refund issued"
        elif refund_policy == "partial":
            # Calculate proportional unused time
            now = timezone.now()
            total_period = (subscription.current_period_end - subscription.current_period_start).total_seconds()
            remaining_period = max(0, (subscription.current_period_end - now).total_seconds())
            prorate_ratio = remaining_period / total_period if total_period > 0 else 0

            refund_amount = int(payment_intent["amount_received"] * prorate_ratio)
            if refund_amount <= 0:
                # print("[Stripe] No remaining period to refund (refund skipped).")
                return

            refund = stripe.Refund.create(charge=charge_id, amount=refund_amount)
            refund_reason = f"Partial refund for unused period ({prorate_ratio*100:.1f}%)"

        # Log it
        StripeEventLog.objects.create(
            event_type="refund.processed",
            data={
                "subscription_id": subscription.id,
                "external_subscription_id": subscription.external_subscription_id,
                "refund_id": refund["id"],
                "amount_refunded": refund.get("amount", 0),
                "currency": refund.get("currency"),
                "policy": refund_policy,
                "reason": refund_reason,
            },
        )

        # print(f"[Stripe] {refund_reason} for subscription {subscription.id}")

    except Exception as e:
        StripeEventLog.objects.create(
            event_type="refund.failed",
            data={
                "subscription_id": subscription.id,
                "external_subscription_id": subscription.external_subscription_id,
                "policy": refund_policy,
                "error": str(e),
            },
        )
        # print(f"[Stripe] Refund failed: {e}")

def sync_subscription_status(subscription):
    """
    Sync local Subscription status with Stripe.
    Useful when webhook events were missed or delayed.
    """
    try:
        if not subscription.external_subscription_id:
            # print(f"[Stripe] Subscription {subscription.id} has no external ID — skipping sync.")
            return

        sub_data = stripe.Subscription.retrieve(subscription.external_subscription_id)

        stripe_status = sub_data["status"]
        current_end_ts = sub_data.get("current_period_end")
        cancel_at_period_end = sub_data.get("cancel_at_period_end", False)

        # Map Stripe status → local status
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "trialing": SubscriptionStatus.TRIALING,
            "canceled": SubscriptionStatus.CANCELED,
            "incomplete": SubscriptionStatus.INCOMPLETE,
            "incomplete_expired": SubscriptionStatus.EXPIRED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "unpaid": SubscriptionStatus.UNPAID,
        }
        local_status = status_map.get(stripe_status, SubscriptionStatus.UNKNOWN)

        # Update local subscription
        subscription.status = local_status
        subscription.cancel_at_period_end = cancel_at_period_end

        if current_end_ts:
            subscription.current_period_end = timezone.make_aware(
                timezone.datetime.fromtimestamp(current_end_ts)
            )

        subscription.save(update_fields=["status", "cancel_at_period_end", "current_period_end"])
        # print(f"[Stripe] Synced subscription {subscription.id} to {local_status}")

    except stripe_error.InvalidRequestError:
        # Subscription might no longer exist on Stripe
        # print(f"[Stripe] Remote subscription not found for {subscription.id}, marking as expired.")
        subscription.status = SubscriptionStatus.EXPIRED
        subscription.save(update_fields=["status"])

    except Exception as e:
        print(f"[Stripe] Failed to sync subscription {subscription.id}: {e}")