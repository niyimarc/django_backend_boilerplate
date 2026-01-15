from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from .conf import get_period_func
from django.utils.translation import gettext_lazy as _

ISO_CURRENCY_MAX_LEN = 10  # Safe room for things like "NGN", "USD"

class Plan(models.Model):
    """
    A purchasable plan with an interval (e.g. monthly, yearly) and flexible entitlements.
    Prices are stored in PlanPrice for multiple currencies.
    """
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    interval = models.CharField(max_length=32, default="monthly")  # Free-form: 'monthly', 'yearly', etc.
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Optional metadata if you need to store arbitrary info (display badge, color, etc.)
    metadata = models.JSONField(blank=True, null=True)
    stripe_product_id = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.interval})"

    def entitlement_for(self, key: str):
        return self.entitlements.filter(key=key).first()

    def get_price(self, currency: str | None = None):
        """
        Pick the best PlanPrice for a currency. If not found, fallback to default (is_default=True) or first.
        """
        qs = self.prices.all()
        if currency:
            price = qs.filter(currency__iexact=currency).first()
            if price:
                return price
        default_price = qs.filter(is_default=True).first()
        return default_price or qs.first()
    
class PlanPrice(models.Model):
    """
    Amount for a plan in a specific currency (multi-currency support).
    """
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="prices")
    currency = models.CharField(max_length=ISO_CURRENCY_MAX_LEN)  # ISO 4217 code, e.g., 'USD', 'NGN', 'EUR'
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ("plan", "currency")
        constraints = [
            # Ensures there can be AT MOST one default price per plan
            models.UniqueConstraint(
                fields=["plan"],
                condition=Q(is_default=True),
                name="unique_default_price_per_plan",
            ),
        ]

    def __str__(self):
        d = " (default)" if self.is_default else ""
        return f"{self.plan.slug}:{self.currency} {self.amount}{d}"

    # ---- NEW: validations to ensure at least one default remains ----
    def clean(self):
        """
        - If setting this instance to default, ensure no other default exists.
        - If unsetting default on an instance that *was* default, ensure another default remains.
        """
        super().clean()

        # fresh DB state
        qs_defaults = PlanPrice.objects.filter(plan=self.plan, is_default=True)
        if self.pk:
            qs_defaults = qs_defaults.exclude(pk=self.pk)

        if self.is_default:
            # You're trying to mark this as default; there must be no other default already.
            if qs_defaults.exists():
                raise ValidationError({"is_default": "Another default price already exists for this plan."})
        else:
            # You're saving with is_default=False. If this object WAS default and you're unsetting it,
            # make sure there is some other default for the plan.
            if self.pk:
                was_default = (
                    PlanPrice.objects.filter(pk=self.pk)
                    .values_list("is_default", flat=True)
                    .first()
                )
                if was_default and not qs_defaults.exists():
                    raise ValidationError(
                        {"is_default": "This is the only default price for this plan. Set another price as default first."}
                    )

    def save(self, *args, **kwargs):
        # Always validate on save so admin / scripts are protected.
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Prevent deleting the only default for a plan.
        """
        if self.is_default:
            other_defaults = PlanPrice.objects.filter(plan=self.plan, is_default=True).exclude(pk=self.pk)
            if not other_defaults.exists():
                raise ValidationError(_("Cannot delete the only default price for this plan. Set another default first."))
        return super().delete(*args, **kwargs)


class Entitlement(models.Model):
    """
    Flexible feature/limit descriptor (no hardcoded keys).
    - enabled: turn the feature on/off for this plan
    - limit_int: numeric quota (e.g., jobs_per_month)
    - limit_str: tier or label (e.g., 'ai', 'template', 'advanced')
    """
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="entitlements")
    key = models.CharField(max_length=80)
    enabled = models.BooleanField(default=False)
    limit_int = models.IntegerField(blank=True, null=True)
    limit_str = models.CharField(max_length=120, blank=True, null=True)
    note = models.CharField(max_length=180, blank=True)

    class Meta:
        unique_together = ("plan", "key")

    def __str__(self):
        return f"{self.plan.slug}:{self.key}"

class SubscriptionStatus(models.TextChoices):
    INCOMPLETE = "incomplete", "Incomplete"
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past Due"
    CANCELED = "canceled", "Canceled"
    EXPIRED = "expired", "Expired"
    UNPAID = "unpaid", "Unpaid"            # ← Add this
    UNKNOWN = "unknown", "Unknown"          # ← Add this (optional safety)

class PaymentProvider(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    PAYSTACK = "paystack", "Paystack"
    FLUTTERWAVE = "flutterwave", "Flutterwave"
    MANUAL = "manual", "Manual/Billing Admin"

class PaymentMethodType(models.TextChoices):
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    USSD = "ussd", "USSD"
    MOBILE_MONEY = "mobile_money", "Mobile Money"
    WALLET = "wallet", "Wallet"
    OTHER = "other", "Other"

class Subscription(models.Model):
    """
    One active (or trialing) subscription per user.
    Captures the currency & unit_amount used at the moment of subscription for audit.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")

    status = models.CharField(max_length=24, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)

    # Captured pricing context
    currency = models.CharField(max_length=ISO_CURRENCY_MAX_LEN, blank=True)
    unit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Optional payment provider hooks
    provider = models.CharField(max_length=24, choices=PaymentProvider.choices, blank=True)
    payment_method_type = models.CharField(
        max_length=24, choices=PaymentMethodType.choices, blank=True
    )
    external_customer_id = models.CharField(max_length=128, blank=True)
    external_subscription_id = models.CharField(max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
                name="uniq_active_subscription_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.plan.slug} ({self.status})"

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return self.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING} and self.current_period_end >= now

    @property
    def next_renewal(self):
        return self.current_period_end

    def renew(self):
        period_func = get_period_func()
        self.current_period_start = timezone.now()
        self.current_period_end = period_func(self.plan.interval, self.current_period_start)
        self.save(update_fields=["current_period_start", "current_period_end"])

class Usage(models.Model):
    """
    Tracks numeric quota usage per subscription and period window for any 'key'.
    """
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="usage")
    key = models.CharField(max_length=80)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    used = models.IntegerField(default=0)

    class Meta:
        unique_together = ("subscription", "key", "period_start", "period_end")

    def __str__(self):
        return f"{self.subscription_id}:{self.key}={self.used}"

class SubscriptionSetting(models.Model):
    """Global configuration for subscription and billing behavior across all users."""

    allow_upgrade = models.BooleanField(
        default=True,
        help_text="If enabled, users can upgrade to a higher-tier plan (e.g., from Basic to Pro).",
    )
    allow_downgrade = models.BooleanField(
        default=True,
        help_text="If enabled, users can downgrade to a lower-tier plan (e.g., from Pro to Basic).",
    )
    allow_free_plan_reuse = models.BooleanField(
        default=False,
        help_text=(
            "If enabled, users can subscribe to the free plan multiple times. "
            "If disabled, users may only use the free plan once."
        ),
    )

    can_cancel = models.BooleanField(
        default=True,
        help_text="If enabled, users can manually cancel their active subscription. "
                "If disabled, only admins can cancel or pause a subscription.",
    )
    auto_charge_on_renewal = models.BooleanField(
        default=True,
        help_text="Automatically charge users when their subscription renews. Disable for manual billing cycles.",
    )
    prorate_on_upgrade = models.BooleanField(
        default=True,
        help_text="If enabled, users upgrading mid-cycle are charged only for the remaining time proportionally.",
    )
    prorate_on_downgrade = models.BooleanField(
        default=False,
        help_text="If enabled, users downgrading mid-cycle receive proportional credit for unused time.",
    )

    downgrade_effect = models.CharField(
        max_length=20,
        choices=[
            ("immediate", "Immediate Switch"),
            ("end_of_period", "After Current Period"),
        ],
        default="end_of_period",
        help_text=(
            "Defines when a downgrade takes effect — "
            "either immediately or after the user's current billing period ends."
        ),
    )

    upgrade_effect = models.CharField(
        max_length=20,
        choices=[
            ("immediate", "Immediate Access"),
            ("next_cycle", "Next Billing Cycle"),
        ],
        default="immediate",
        help_text=(
            "Defines when an upgrade takes effect — "
            "grant access immediately or defer until the next billing cycle."
        ),
    )

    cancel_effect = models.CharField(
        max_length=20,
        choices=[
            ("immediate", "Immediate Termination"),
            ("end_of_period", "After Current Period"),
        ],
        default="end_of_period",
        help_text="Defines when cancellation takes effect — immediately or after the current billing period ends.",
    )

    refund_policy = models.CharField(
        max_length=20,
        choices=[
            ("none", "No Refunds"),
            ("partial", "Prorated Refunds"),
            ("full", "Full Refunds"),
        ],
        default="partial",
        help_text=(
            "Determines how refunds are handled during cancellations or downgrades: "
            "no refund, partial/prorated, or full refund."
        ),
    )

    enable_multiple_gateways = models.BooleanField(
        default=True,
        help_text="Allow the system to use more than one payment gateway (e.g., Stripe + Paystack).",
    )

    default_provider = models.CharField(
        max_length=30,
        choices=[
            ("stripe", "Stripe"),
            ("paystack", "Paystack"),
            ("flutterwave", "Flutterwave"),
            ("manual", "Manual"),
        ],
        default="stripe",
        help_text="Select the default payment provider for new subscriptions.",
    )

    success_url = models.URLField(
        blank=True,
        help_text="Frontend URL users are redirected to after a successful payment.",
    )

    cancel_url = models.URLField(
        blank=True,
        help_text="Frontend URL users are redirected to if they cancel a payment.",
    )
    
    policy_text = models.TextField(
        blank=True,
        help_text="Automatically generated subscription policy text for users to understand payment rules.",
    )
    
    updated_at = models.DateTimeField(
        auto_now=True, help_text="Automatically updated when any setting changes."
    )
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Date and time when this setting record was created."
    )

    class Meta:
        verbose_name = "Subscription Setting"
        verbose_name_plural = "Subscription Settings"

    def clean(self):
        """Ensure only one SubscriptionSetting exists globally."""
        if SubscriptionSetting.objects.exclude(id=self.id).exists():
            raise ValidationError("Only one global SubscriptionSetting instance is allowed.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return "Global Subscription Settings"


class PaymentProviderSetting(models.Model):
    """Configuration for individual payment providers (e.g., Stripe, Paystack, etc.)."""

    subscription_setting = models.ForeignKey(
        SubscriptionSetting,
        related_name="providers",
        on_delete=models.CASCADE,
        help_text="The global subscription setting this provider configuration belongs to.",
    )

    provider = models.CharField(
        max_length=30,
        choices=[
            ("stripe", "Stripe"),
            ("paystack", "Paystack"),
            ("flutterwave", "Flutterwave"),
            ("manual", "Manual"),
        ],
        help_text="The payment provider this configuration applies to.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Enable or disable this provider globally. Disabled providers won't process payments.",
    )

    priority = models.PositiveIntegerField(
        default=1,
        help_text="Defines provider priority. Lower numbers mean higher preference when multiple gateways are enabled.",
    )

    additional_settings = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Optional configuration for provider-specific settings "
            "(e.g., currency, region, webhook preferences, or custom headers)."
        ),
    )

    class Meta:
        unique_together = ("subscription_setting", "provider")
        ordering = ["priority"]
        verbose_name = "Payment Provider Setting"
        verbose_name_plural = "Payment Provider Settings"

    def __str__(self):
        return f"{self.provider} (Priority {self.priority})"

class StripeEventLog(models.Model):
    event_type = models.CharField(max_length=100)
    data = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)