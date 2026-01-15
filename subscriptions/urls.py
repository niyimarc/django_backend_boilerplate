from django.urls import path
from .view_stripe import StripeCheckoutView, StripeWebhookView
from .views import (
    PlanListView, 
    MySubscriptionView, 
    RemainingQuotaView, 
    SubscriptionUpgradeView, 
    SubscriptionDowngradeView, 
    SubscriptionCancelView,
    SubscriptionPolicyView
    )

urlpatterns = [
    path("api/subscription/plans/", PlanListView.as_view(), name="sub_plans"),
    path("api/subscription/my_subscription/", MySubscriptionView.as_view(), name="my_subscription"),
    path("api/subscription/quota/", RemainingQuotaView.as_view(), name="sub_quota"),
    path("api/subscriptions/upgrade/", SubscriptionUpgradeView.as_view(), name="subscription_upgrade"),
    path("api/subscriptions/downgrade/", SubscriptionDowngradeView.as_view(), name="subscription_downgrade"),
    path("api/subscriptions/cancel/", SubscriptionCancelView.as_view(), name="subscription_cancel"),
    path("api/subscriptions/policy/", SubscriptionPolicyView.as_view(), name="subscription_policy"),
    path("api/stripe/webhook/", StripeWebhookView.as_view(), name="stripe_webhook"),
    path("api/stripe/checkout/", StripeCheckoutView.as_view(), name="stripe_checkout"),
]
