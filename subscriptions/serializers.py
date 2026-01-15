from rest_framework import serializers
from .models import Plan, PlanPrice, Entitlement, Subscription
from .utils import label_for_key, value_label_for_key, currency_symbol, format_money, order_for_key
from django.utils import timezone

class PlanPriceSerializer(serializers.ModelSerializer):
    symbol = serializers.SerializerMethodField()
    display = serializers.SerializerMethodField()

    class Meta:
        model = PlanPrice
        fields = ["currency", "amount", "is_default", "symbol", "display"]

    def get_symbol(self, obj): return currency_symbol(obj.currency)
    def get_display(self, obj): return format_money(obj.amount, obj.currency)

class EntitlementSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    value_display = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()

    class Meta:
        model = Entitlement
        fields = ["key", "enabled", "limit_int", "limit_str", "note","label", "value_display", "order"]
    
    def get_label(self, obj): return label_for_key(obj.key)
    def get_value_display(self, obj):
        if obj.limit_int is not None: return str(obj.limit_int)
        if obj.limit_str: return value_label_for_key(obj.key, obj.limit_str)
        return "Yes" if obj.enabled else "No"
    
    def get_order(self, obj):
        return order_for_key(obj.key)

class PlanSerializer(serializers.ModelSerializer):
    prices = serializers.SerializerMethodField()
    selected_price = serializers.SerializerMethodField()
    entitlements = EntitlementSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = ["slug", "name", "description", "interval", "is_active", "metadata", "prices", "entitlements", "selected_price"]

    def get_selected_price(self, obj):
        currency = self.context.get("currency")
        price = obj.get_price(currency)  # uses your Plan.get_price logic
        return PlanPriceSerializer(price, context=self.context).data if price else None
    
    def get_prices(self, obj):
        mode = self.context.get("prices_mode", "all")
        currency = self.context.get("currency")
        if mode == "none":
            return []
        if mode == "selected":
            price = obj.get_price(currency)
            return [PlanPriceSerializer(price, context=self.context).data] if price else []
        # default: all
        return PlanPriceSerializer(obj.prices.all(), many=True, context=self.context).data

class CompactPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["name", "slug", "interval"]

class SubscriptionSerializer(serializers.ModelSerializer):
    plan = CompactPlanSerializer(read_only=True)
    current_period_start = serializers.SerializerMethodField()
    current_period_end = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "plan",
            "status",
            "currency",
            "unit_amount",
            "provider",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
        ]

    def get_current_period_start(self, obj):
        if obj.current_period_start:
            return timezone.localtime(obj.current_period_start).strftime("%b %d, %Y, %I:%M %p")
        return None

    def get_current_period_end(self, obj):
        if obj.current_period_end:
            return timezone.localtime(obj.current_period_end).strftime("%b %d, %Y, %I:%M %p")
        return None