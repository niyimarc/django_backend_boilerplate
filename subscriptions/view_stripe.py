from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
from django.views import View
from django.utils import timezone
from decimal import Decimal
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from auth_core.views import PrivateUserViewMixin
from subscriptions.payment_gateway.router import get_gateway, get_config
from .utils import get_subscription_setting
from .models import Plan, Subscription, SubscriptionStatus


class StripeCheckoutView(PrivateUserViewMixin, APIView):
    """
    Creates a Stripe Checkout Session for an authenticated user.
    Ensures user has only one active subscription at a time.
    Allows upgrade from free plans.
    Prevents reusing free plan after it's been used once.
    Prevents switching from paid → free while active.
    """

    def post(self, request, *args, **kwargs):
        plan_slug = request.data.get("plan_slug")
        plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()
        if not plan:
            return Response({"error": "Plan not found."}, status=404)

        price = plan.get_price()
        if not price:
            return Response({"error": "This plan has no valid price."}, status=400)

        new_plan_price = Decimal(price.amount or 0)

        # --- Get subscription settings ---
        settings = get_subscription_setting()

        # --- Check for existing active subscription ---
        active_sub = Subscription.objects.filter(
            user=request.user,
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
            current_period_end__gte=timezone.now(),
        ).first()

        # --- Check if user has ever used the free plan before ---
        has_used_free_plan_before = Subscription.objects.filter(
            user=request.user,
            plan=plan,
            unit_amount=0,
        ).exists()

        # --- Respect admin rule: disallow reusing free plan ---
        if not settings.allow_free_plan_reuse:
            if new_plan_price == 0 and has_used_free_plan_before:
                return Response(
                    {
                        "error": (
                            "You have already used the free plan. "
                            "Please select a paid plan to continue."
                        ),
                        "plan": plan.name,
                    },
                    status=400,
                )

        # --- Handle existing active subscription rules ---
        if active_sub:
            current_plan_price = Decimal(active_sub.unit_amount or 0)

            # --- Prevent repurchasing the same plan ---
            if active_sub.plan_id == plan.id:
                return Response(
                    {
                        "error": (
                            "You are already subscribed to this plan. "
                            "You can cancel, upgrade, downgrade, or wait until it expires before purchasing another plan."
                        ),
                        "current_plan": active_sub.plan.name,
                        "current_plan_price": str(current_plan_price),
                    },
                    status=400,
                )

            # --- Prevent switching between two paid plans ---
            if current_plan_price > 0 and new_plan_price > 0:
                return Response(
                    {
                        "error": (
                            "You already have an active paid plan. "
                            "Please cancel or wait until it expires before purchasing another plan."
                        ),
                        "current_plan": active_sub.plan.name,
                        "current_plan_price": str(current_plan_price),
                    },
                    status=400,
                )

            # --- ✅ Prevent switching from PAID → FREE while active ---
            if current_plan_price > 0 and new_plan_price == 0:
                return Response(
                    {
                        "error": (
                            "You cannot switch from a paid plan to a free plan while your current plan is still active. "
                            "Please wait until your current subscription expires or cancel it first."
                        ),
                        "current_plan": active_sub.plan.name,
                        "current_plan_price": str(current_plan_price),
                    },
                    status=400,
                )

        # --- Proceed to Stripe checkout (only if all checks pass) ---
        provider = "stripe"
        gateway = get_gateway(provider)
        config = get_config(provider)

        if hasattr(gateway, "configure"):
            gateway.configure(config)

        session = gateway.create_checkout_session(
            request.user,
            plan,
            config["success_url"],
            config["cancel_url"],
        )

        return Response(
            {
                "checkout_url": session.url,
                "message": (
                    "Redirecting to checkout..."
                    if new_plan_price > 0
                    else "Free plan activation — no payment required."
                ),
            },
            status=200,
        )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    """
    Handles Stripe webhooks using the modular payment router.
    """
    provider = "stripe"

    def post(self, request, *args, **kwargs):
        gateway = get_gateway(self.provider)
        keys = get_config(self.provider)

        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

        try:
            import stripe
            event = stripe.Webhook.construct_event(
                payload, sig_header, keys["webhook_secret"]
            )
        except ValueError:
            return HttpResponse("Invalid payload", status=400)
        except stripe.error.SignatureVerificationError:
            return HttpResponse("Invalid signature", status=400)

        if hasattr(gateway, "configure"):
            gateway.configure(keys)

        try:
            gateway.handle_webhook(event)
        except Exception as e:
            # print(f"[Webhook Error: {self.provider}] {e}")
            return HttpResponse(status=500)

        return HttpResponse(status=200)

    def get(self, request, *args, **kwargs):
        return HttpResponse("Stripe webhook endpoint.", status=200)
