from django.db import transaction
from django.utils import timezone
from .models import Plan, PlanPrice, Subscription, Usage, SubscriptionStatus
from .conf import get_setting, load_callable

def _period_end(plan, start=None):
    period_func = load_callable(get_setting("PERIOD_FUNC"))
    return period_func(plan.interval, start)

@transaction.atomic
def start_or_change_subscription(user, plan_slug: str, *, currency: str | None = None, end_current_now=True) -> Subscription:
    """
    Start or change a user's subscription. Captures price in the requested currency if available,
    otherwise uses the plan's default price (PlanPrice.is_default=True) or first available price.
    """
    plan = Plan.objects.select_related().get(slug=plan_slug, is_active=True)
    now = timezone.now()

    # Find desired price
    price: PlanPrice | None = plan.get_price(currency)

    # Existing active/trialing?
    sub = Subscription.objects.filter(
        user=user, status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
    ).select_for_update().first()

    if not sub:
        return Subscription.objects.create(
            user=user,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=_period_end(plan, now),
            currency=(price.currency if price else get_setting("DEFAULT_CURRENCY")),
            unit_amount=(price.amount if price else 0),
        )

    # Change plan (no proration in MVP)
    if end_current_now:
        sub.current_period_start = now
        sub.current_period_end = _period_end(plan, now)

    sub.plan = plan
    sub.status = SubscriptionStatus.ACTIVE
    sub.cancel_at_period_end = False
    sub.currency = (price.currency if price else sub.currency or get_setting("DEFAULT_CURRENCY"))
    sub.unit_amount = (price.amount if price else sub.unit_amount)
    sub.save()
    return sub

def cancel_at_period_end(user) -> Subscription | None:
    sub = Subscription.objects.filter(
        user=user, status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
    ).first()
    if not sub:
        return None
    sub.cancel_at_period_end = True
    sub.save(update_fields=["cancel_at_period_end"])
    return sub

def _get_or_create_usage(sub: Subscription, key: str) -> Usage:
    return Usage.objects.get_or_create(
        subscription=sub,
        key=key,
        period_start=sub.current_period_start,
        period_end=sub.current_period_end,
        defaults={"used": 0},
    )[0]

def get_remaining_quota(user, key: str) -> int | None:
    """
    Returns:
      - int >= 0 for finite quota left
      - None for unlimited (enabled True + limit_int is None)
      - 0 if not enabled/no active subscription
    """
    sub = Subscription.objects.filter(
        user=user, status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
    ).select_related("plan").first()
    if not sub or not sub.is_active:
        return 0

    ent = sub.plan.entitlement_for(key)
    if not ent or not ent.enabled:
        return 0

    if ent.limit_int is None:
        return None  # unlimited

    usage = _get_or_create_usage(sub, key)
    return max(ent.limit_int - usage.used, 0)

def record_quota_usage(user, key: str, amount: int = 1) -> bool:
    """
    Returns True if recorded, False if it would exceed quota or not enabled.
    """
    sub = Subscription.objects.filter(
        user=user, status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
    ).select_related("plan").first()
    if not sub or not sub.is_active:
        return False

    ent = sub.plan.entitlement_for(key)
    if not ent or not ent.enabled:
        return False

    usage = _get_or_create_usage(sub, key)
    if ent.limit_int is None:
        usage.used += amount
        usage.save(update_fields=["used"])
        return True

    if usage.used + amount > ent.limit_int:
        return False

    usage.used += amount
    usage.save(update_fields=["used"])
    return True
