import stripe
from subscriptions.payment_gateway.stripe import configure
from subscriptions.payment_gateway.router import get_config
from subscriptions.utils import get_subscription_setting

def ensure_product_for_plan(plan):
    """
    Ensure the given plan has a matching Stripe Product.
    Keeps Stripe API logic isolated from Django model definitions.
    """
    settings = get_subscription_setting()
    provider = settings.providers.filter(provider="stripe", is_active=True).first()
    if not provider:
        raise Exception("No active Stripe provider configuration found.")

    # ✅ Use global router to load proper Stripe configuration
    config = get_config("stripe")
    configure(config)

    if not plan.stripe_product_id:
        product = stripe.Product.create(
            name=plan.name,
            description=plan.description or "",
            active=True,
            metadata={"slug": plan.slug, "interval": plan.interval},
        )
        plan.stripe_product_id = product.id
        plan.save(update_fields=["stripe_product_id"])
        # print(f"[Stripe Sync] Created product {product.id} for plan '{plan.slug}'")
        return product.id

    try:
        product = stripe.Product.retrieve(plan.stripe_product_id)
        if not product["active"]:
            stripe.Product.modify(plan.stripe_product_id, active=True)
            # print(f"[Stripe Sync] Reactivated product {plan.stripe_product_id} ({plan.slug})")
    except Exception as e:
        # print(f"[Stripe Sync] Error retrieving product {plan.stripe_product_id}: {e}")
        plan.stripe_product_id = None
        plan.save(update_fields=["stripe_product_id"])
        return ensure_product_for_plan(plan)

    return plan.stripe_product_id
