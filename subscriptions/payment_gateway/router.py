from importlib import import_module
from django.conf import settings
from subscriptions.models import PaymentProviderSetting, SubscriptionSetting


GATEWAY_MAP = {
    "stripe": "subscriptions.payment_gateway.stripe",
    "paystack": "subscriptions.payment_gateway.paystack",
    "flutterwave": "subscriptions.payment_gateway.flutterwave",
    "manual": "subscriptions.payment_gateway.manual",
}


def get_gateway(provider_name: str):
    """Dynamically import and return the payment gateway module."""
    provider_name = (provider_name or "").lower().strip()
    if provider_name not in GATEWAY_MAP:
        raise ValueError(f"Unsupported payment provider: {provider_name}")
    return import_module(GATEWAY_MAP[provider_name])


def get_config(provider_name: str) -> dict:
    """
    Return combined configuration for the selected provider:
    - Secret keys (from settings)
    - Webhook keys
    - Success/Cancel URLs (from SubscriptionSetting)
    """

    provider_name = (provider_name or "").lower()

    # --- Fetch global SubscriptionSetting (should always exist) ---
    subscription_config = SubscriptionSetting.objects.first()

    success_url = ""
    cancel_url = ""

    if subscription_config:
        success_url = subscription_config.success_url or ""
        cancel_url = subscription_config.cancel_url or ""

    # --- 2️⃣ Optionally validate that the provider is enabled ---
    provider_config = PaymentProviderSetting.objects.filter(
        provider=provider_name, is_active=True
    ).order_by("priority").first()

    if not provider_config:
        raise ValueError(f"No active configuration found for provider: {provider_name}")

    # --- Get secret keys from environment/settings ---
    if provider_name == "stripe":
        keys = {
            "secret_key": getattr(settings, "STRIPE_SECRET_KEY", ""),
            "webhook_secret": getattr(settings, "STRIPE_WEBHOOK_SECRET", ""),
        }
    elif provider_name == "paystack":
        keys = {"secret_key": getattr(settings, "PAYSTACK_SECRET_KEY", "")}
    elif provider_name == "flutterwave":
        keys = {"secret_key": getattr(settings, "FLUTTERWAVE_SECRET_KEY", "")}
    else:
        keys = {}

    # --- Combine all configuration into one dict ---
    return {
        "provider": provider_name,
        "success_url": success_url,
        "cancel_url": cancel_url,
        **keys,
    }