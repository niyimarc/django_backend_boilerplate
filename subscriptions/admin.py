from django.contrib import admin, messages
from django import forms
from django.utils import timezone
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from subscriptions.payment_gateway.router import get_gateway, get_config
from .models import Plan, PlanPrice, Entitlement, Subscription, Usage, StripeEventLog, SubscriptionSetting, PaymentProviderSetting
from .conf import get_setting

class EntitlementForm(forms.ModelForm):
    class Meta:
        model = Entitlement
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = get_setting("ENTITLEMENT_KEYS")
        if isinstance(allowed, (list, tuple)) and len(allowed) > 0:
            self.fields["key"] = forms.ChoiceField(choices=[(k, k) for k in allowed])

# inline formset validation for prices
class PlanPriceInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        defaults = 0
        seen_currencies = set()
        kept_rows = 0

        for form in self.forms:
            # Skip forms that didn't validate to avoid KeyError
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if cd.get("DELETE"):
                continue

            kept_rows += 1

            currency = (cd.get("currency") or "").upper()
            if currency:
                if currency in seen_currencies:
                    raise ValidationError("Duplicate currency entries are not allowed for the same plan.")
                seen_currencies.add(currency)

            if cd.get("is_default"):
                defaults += 1

        if kept_rows == 0:
            raise ValidationError("At least one price is required for a plan.")

        if defaults == 0:
            raise ValidationError("At least one default price is required for a plan.")

        if defaults > 1:
            raise ValidationError("Only one price can be set as default for a plan.")

class PlanPriceInline(admin.TabularInline):
    model = PlanPrice
    extra = 0
    formset = PlanPriceInlineFormSet
    min_num = 1
    validate_min = True

class EntitlementInline(admin.TabularInline):
    model = Entitlement
    form = EntitlementForm
    extra = 0

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "interval", "is_active", "sort_order")
    list_filter = ("is_active", "interval")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PlanPriceInline, EntitlementInline]

class ActiveStatusFilter(SimpleListFilter):
    title = "Active Status"
    parameter_name = "is_active"

    def lookups(self, request, model_admin):
        return [
            ("active", "Currently Active"),
            ("inactive", "Inactive / Ended"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "active":
            return queryset.filter(
                status__in=["active", "trialing"],
                current_period_end__gte=now
            )
        elif self.value() == "inactive":
            return queryset.exclude(
                status__in=["active", "trialing"],
                current_period_end__gte=now
            )
        return queryset
    
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "status",
        "currency",
        "unit_amount",
        "current_period_start",
        "current_period_end",
        "is_active_display",
        "duration_days",
    )
    list_filter = (
        "status",
        ActiveStatusFilter,
        "plan__interval",
        "currency",
        "plan__slug",
        "provider",
    )
    search_fields = (
        "user__username",
        "user__email",
        "external_subscription_id",
        "external_customer_id",
    )
    ordering = ("-current_period_end",)

    # Add this line so actions appear
    actions = ["sync_from_gateway", "cancel_from_gateway"]

    # --- Custom Columns ---
    def is_active_display(self, obj):
        return "✅ Active" if obj.is_active else "❌ Inactive"
    is_active_display.short_description = "Active?"
    is_active_display.admin_order_field = "current_period_end"

    def duration_days(self, obj):
        if obj.current_period_start and obj.current_period_end:
            return (obj.current_period_end - obj.current_period_start).days
        return "-"
    duration_days.short_description = "Duration (days)"

    # --- Quick Filters ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("plan", "user")

    @admin.action(description="🔄 Sync from payment gateway")
    def sync_from_gateway(self, request, queryset):
        """
        Fetch and refresh subscription info from the provider (e.g., Stripe, Paystack, etc.).
        Each gateway must implement `sync_subscription_status(subscription)`.
        """
        updated = 0
        errors = 0

        for sub in queryset:
            try:
                if not sub.provider:
                    messages.warning(
                        request,
                        f"Subscription {sub.id} has no provider — skipping.",
                    )
                    continue

                config = get_config(sub.provider)
                gateway = get_gateway(sub.provider)

                if hasattr(gateway, "configure"):
                    gateway.configure(config)

                if hasattr(gateway, "sync_subscription_status"):
                    gateway.sync_subscription_status(sub)
                    updated += 1
                else:
                    messages.warning(
                        request,
                        f"{sub.provider.title()} gateway does not support syncing yet.",
                    )
            except Exception as e:
                errors += 1
                self.message_user(
                    request,
                    f"❌ Error syncing {sub.provider} subscription {sub.id}: {e}",
                    level=messages.ERROR,
                )

        self.message_user(
            request,
            f"✅ Synced {updated} subscription(s). {'❌ Errors: ' + str(errors) if errors else ''}",
            level=messages.SUCCESS if errors == 0 else messages.WARNING,
        )

    @admin.action(description="🚫 Cancel via payment gateway")
    def cancel_from_gateway(self, request, queryset):
        """
        Cancels the subscription remotely via payment gateway (respects refund & cancel rules).
        """
        canceled = 0
        errors = 0

        from subscriptions.utils import get_subscription_setting

        settings = get_subscription_setting()

        for sub in queryset:
            try:
                if not sub.provider:
                    messages.warning(
                        request,
                        f"Subscription {sub.id} has no provider — skipping.",
                    )
                    continue

                config = get_config(sub.provider)
                gateway = get_gateway(sub.provider)

                if hasattr(gateway, "configure"):
                    gateway.configure(config)

                if hasattr(gateway, "process_cancellation"):
                    gateway.process_cancellation(
                        sub,
                        settings.cancel_effect,
                        settings.refund_policy,
                    )
                    canceled += 1
                else:
                    messages.warning(
                        request,
                        f"{sub.provider.title()} gateway does not support remote cancellation yet.",
                    )
            except Exception as e:
                errors += 1
                self.message_user(
                    request,
                    f"❌ Error cancelling {sub.provider} subscription {sub.id}: {e}",
                    level=messages.ERROR,
                )

        self.message_user(
            request,
            f"🚫 Cancelled {canceled} subscription(s). {'❌ Errors: ' + str(errors) if errors else ''}",
            level=messages.SUCCESS if errors == 0 else messages.WARNING,
        )

    def has_add_permission(self, request):
        # Subscriptions should only come from gateways, not manually
        return False


@admin.register(Usage)
class UsageAdmin(admin.ModelAdmin):
    list_display = ("subscription", "key", "used", "period_start", "period_end")
    list_filter = ("key",)

@admin.register(StripeEventLog)
class StripeEventLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "received_at", "short_id")
    list_filter = ("event_type",)
    search_fields = ("event_type", "data")
    ordering = ("-received_at",)

    def short_id(self, obj):
        """
        Show a short identifier for debugging (from Stripe event ID if present).
        """
        stripe_id = obj.data.get("id") if isinstance(obj.data, dict) else None
        return stripe_id or "—"
    short_id.short_description = "Stripe Event ID"

    def has_add_permission(self, request):
        # Webhooks create these automatically
        return False

    def has_change_permission(self, request, obj=None):
        # Prevent manual edits
        return False
    
class PaymentProviderInline(admin.TabularInline):
    model = PaymentProviderSetting
    extra = 0
    fields = (
        "provider",
        "is_active",
        "priority",
    )

@admin.register(SubscriptionSetting)
class SubscriptionSettingAdmin(admin.ModelAdmin):
    inlines = [PaymentProviderInline]
    list_display = (
        "default_provider",
        "allow_upgrade",
        "allow_downgrade",
        "auto_charge_on_renewal",
        "refund_policy",
        "enable_multiple_gateways",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return SubscriptionSetting.objects.count() == 0