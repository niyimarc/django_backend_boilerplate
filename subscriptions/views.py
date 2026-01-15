from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from auth_core.views import PrivateUserViewMixin, PublicViewMixin
from .models import Plan, Subscription, SubscriptionSetting
from .serializers import PlanSerializer, SubscriptionSerializer
from .services import start_or_change_subscription, cancel_at_period_end, get_remaining_quota
from .utils import build_comparison, get_subscription_setting
from .pagination import PlanPagination, SubscriptionPagination
from subscriptions.payment_gateway.router import get_gateway, get_config


class PlanListView(PublicViewMixin, generics.ListAPIView):
    """
    GET /api/subscription/plans/
    Returns all active plans (non-paginated) with optional interval filtering.
    """
    serializer_class = PlanSerializer

    def get_queryset(self):
        qs = Plan.objects.filter(is_active=True)
        raw = self.request.query_params.getlist("interval") or []
        if not raw:
            single = (self.request.query_params.get("interval") or "").strip()
            if single:
                raw = [single]

        intervals = []
        for item in raw:
            for part in item.split(","):
                part = part.strip().lower()
                if part and part != "all":
                    intervals.append(part)

        if intervals:
            qs = qs.filter(interval__in=intervals)

        qs = qs.prefetch_related("prices", "entitlements").order_by("sort_order", "name")

        # print(f"\n[DEBUG] get_queryset() -> intervals={intervals or 'all'} | count={qs.count()}")
        # for plan in qs:
        #     print(f"   ↳ {plan.slug} ({plan.interval}) | active={plan.is_active}")

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["currency"] = (self.request.query_params.get("currency") or "").strip().upper() or None
        ctx["prices_mode"] = (self.request.query_params.get("prices") or "all").strip().lower()
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        plans = serializer.data
        comparison = build_comparison(plans)

        # Directly return the complete data (no pagination)
        return Response({
            "plans": plans,
            "comparison": comparison
        })

    
@method_decorator(csrf_exempt, name="dispatch")
class MySubscriptionView(PrivateUserViewMixin, generics.ListAPIView):
    """
    Returns all subscriptions (active, canceled, expired, etc.)
    for the logged-in user with custom pagination.
    """
    serializer_class = SubscriptionSerializer
    pagination_class = SubscriptionPagination

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user).order_by("-created_at")

class RemainingQuotaView(PrivateUserViewMixin, generics.GenericAPIView):
    """
    Private: get remaining quota for a given key.
    GET /api/subscriptions/quota/?key=jobs_per_month
    GET /api/subscriptions/quota/?key=jobs_per_day
    """
    def get(self, request):
        key = request.GET.get("key")
        if not key:
            return Response({"detail": "key is required"}, status=status.HTTP_400_BAD_REQUEST)
        left = get_remaining_quota(request.user, key)
        return Response({"key": key, "remaining": left})

class SubscriptionUpgradeView(PrivateUserViewMixin, APIView):
    """
    Upgrade endpoint for all gateways.
    """
    def post(self, request, *args, **kwargs):
        plan_slug = request.data.get("plan_slug")
        settings = get_subscription_setting()

        provider = (
            (request.data.get("payment_gateway") or settings.default_provider or "stripe")
            .lower()
        )

        if not plan_slug or not provider:
            return Response({"error": "Missing plan_slug or payment_gateway."}, status=400)

        plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()
        if not plan:
            return Response({"error": "Target plan not found."}, status=404)

        subscription = Subscription.objects.filter(user=request.user, status="active").first()
        if not subscription:
            return Response({"error": "No active subscription found."}, status=400)

        # Prevent upgrading to the same plan
        if subscription.plan_id == plan.id:
            return Response({"error": "You are already on this plan."}, status=400)

        if not settings.allow_upgrade:
            return Response({"error": "Upgrading is currently disabled by admin."}, status=403)

        # Ensure this is truly an upgrade
        old_price = subscription.unit_amount or 0
        new_price = plan.get_price().amount
        if new_price <= old_price:
            return Response({"error": "Selected plan is not an upgrade."}, status=400)

        try:
            config = get_config(provider)
            gateway = get_gateway(provider)
            if hasattr(gateway, "configure"):
                gateway.configure(config)

            gateway.process_upgrade(subscription, plan)
            return Response({
                "message": f"Subscription upgraded to {plan.name} successfully.",
                "provider": provider,
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

class SubscriptionDowngradeView(PrivateUserViewMixin, APIView):
    def post(self, request, *args, **kwargs):
        plan_slug = request.data.get("plan_slug")
        settings = get_subscription_setting()

        provider = (
            (request.data.get("payment_gateway") or settings.default_provider or "stripe")
            .lower()
        )

        if not plan_slug or not provider:
            return Response({"error": "Missing plan_slug or payment_gateway."}, status=400)

        plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()
        if not plan:
            return Response({"error": "Target plan not found."}, status=404)

        subscription = Subscription.objects.filter(user=request.user, status="active").first()
        if not subscription:
            return Response({"error": "No active subscription found."}, status=400)

        # Prevent downgrading to the same plan
        if subscription.plan_id == plan.id:
            return Response({"error": "You are already on this plan."}, status=400)

        if not settings.allow_downgrade:
            return Response({"error": "Downgrading is currently disabled by admin."}, status=403)

        old_price = subscription.unit_amount or 0
        new_price = plan.get_price().amount
        if new_price >= old_price:
            return Response({"error": "Selected plan is not a downgrade."}, status=400)

        try:
            config = get_config(provider)
            gateway = get_gateway(provider)
            if hasattr(gateway, "configure"):
                gateway.configure(config)

            gateway.process_downgrade(subscription, plan)
            return Response({
                "message": f"Subscription downgraded to {plan.name} successfully.",
                "provider": provider,
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        
class SubscriptionCancelView(PrivateUserViewMixin, APIView):
    """
    Allows users to cancel their subscription — even if it appears expired locally.
    This ensures remote subscriptions (Stripe/Paystack/etc.) are also stopped.
    Respects global admin settings:
      - can_cancel
      - cancel_effect
      - refund_policy
    """

    def post(self, request, *args, **kwargs):
        settings = get_subscription_setting()

        # Default priority: frontend → admin setting → stripe
        provider = (
            (request.data.get("payment_gateway") or settings.default_provider or "stripe")
            .lower()
        )

        if not provider:
            return Response({"error": "Missing payment_gateway."}, status=400)

        # Find most recent subscription (active or expired)
        subscription = (
            Subscription.objects.filter(user=request.user)
            .order_by("-current_period_end")
            .first()
        )
        if not subscription:
            return Response({"error": "No subscription record found."}, status=404)

        # If admin has disabled cancellation entirely
        if not settings.can_cancel:
            return Response(
                {"error": "Subscription cancellation is disabled by the administrator."},
                status=403,
            )

        try:
            # Load gateway dynamically
            config = get_config(provider)
            gateway = get_gateway(provider)
            if hasattr(gateway, "configure"):
                gateway.configure(config)

            cancel_effect = settings.cancel_effect
            refund_policy = settings.refund_policy

            # Always check with gateway if still active remotely
            if hasattr(gateway, "process_cancellation"):
                gateway.process_cancellation(subscription, cancel_effect, refund_policy)
            else:
                # Fallback local cancellation
                subscription.status = "canceled"
                subscription.save(update_fields=["status"])

            # Construct message
            if subscription.is_active:
                message = (
                    "Your subscription has been cancelled and access revoked immediately."
                    if cancel_effect == "immediate"
                    else "Your subscription will remain active until your current billing period ends."
                )
            else:
                message = (
                    "Your subscription is already inactive locally, but we have ensured "
                    "it’s fully cancelled on the payment provider to prevent renewal."
                )

            return Response(
                {
                    "message": message,
                    "effect": cancel_effect,
                    "refund_policy": refund_policy,
                    "provider": provider,
                    "status": subscription.status,
                },
                status=200,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=500)
        
class SubscriptionPolicyView(PublicViewMixin, APIView):
    """
    Returns the current subscription & payment policy in HTML format.
    """
    def get(self, request, *args, **kwargs):
        setting = SubscriptionSetting.objects.first()
        if not setting or not setting.policy_text:
            return Response(
                {"error": "Subscription policy not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "last_updated": setting.updated_at,
                "policy_html": setting.policy_text,
            },
            status=status.HTTP_200_OK,
        )