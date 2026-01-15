from celery import shared_task
from django.utils import timezone
from subscriptions.models import Subscription, SubscriptionStatus, SubscriptionSetting
from subscriptions.payment_gateway.router import get_gateway, get_config


@shared_task(name="subscriptions.sync_all_payment_providers")
def sync_all_payment_providers():
    """
    Synchronize active subscriptions for all enabled payment providers.
    Uses SubscriptionSetting to determine which gateways are active.
    """
    print(f"[Celery] Starting full subscription sync at {timezone.now()}")

    # Try to get global settings
    settings = SubscriptionSetting.objects.first()
    if not settings:
        print("[Celery] No SubscriptionSetting found — aborting sync.")
        return

    # Determine which providers are enabled
    if settings.enable_multiple_gateways:
        providers = [
            provider.provider.lower()
            for provider in settings.providers.filter(is_active=True)
        ]
    else:
        providers = [settings.default_provider.lower()]

    if not providers:
        print("[Celery] No active payment providers — nothing to sync.")
        return

    print(f"[Celery] Syncing subscriptions for providers: {providers}")

    total_synced = 0
    total_failed = 0

    for provider in providers:
        print(f"[Celery] --- Syncing provider: {provider} ---")
        subs = Subscription.objects.filter(
            provider=provider,
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
        )

        print(f"[Celery] Found {subs.count()} subscriptions for {provider}.")

        try:
            config = get_config(provider)
            gateway = get_gateway(provider)
            if hasattr(gateway, "configure"):
                gateway.configure(config)
        except Exception as e:
            print(f"[Celery] Failed to load gateway for {provider}: {e}")
            continue

        for sub in subs:
            try:
                if hasattr(gateway, "sync_subscription_status"):
                    gateway.sync_subscription_status(sub)
                    total_synced += 1
                else:
                    print(f"[Celery] Gateway {provider} has no sync_subscription_status().")
            except Exception as e:
                total_failed += 1
                print(f"[Celery] Sync failed for {provider} subscription {sub.id}: {e}")

    print(
        f"[Celery] Sync completed at {timezone.now()}: "
        f"{total_synced} succeeded, {total_failed} failed."
    )
 