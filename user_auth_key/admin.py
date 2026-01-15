from django.contrib import admin
from .models import UserKeyPair, KeyRegenerationLog, PrivateKeyAccessLog


@admin.register(UserKeyPair)
class UserKeyPairAdmin(admin.ModelAdmin):
    list_display = ("user", "masked_private_key", "public_key", "created_at", "revoked")
    search_fields = ("user__username", "private_key")
    list_filter = ("revoked", "created_at")
    readonly_fields = ("public_key", "masked_private_key", "created_at")

    fieldsets = (
        ("User & Key Info", {
            "fields": ("user", "masked_private_key", "public_key", "private_key", "revoked")
        }),
        ("Timestamps", {
            "fields": ("created_at",),
        }),
    )


@admin.register(KeyRegenerationLog)
class KeyRegenerationLogAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp")
    search_fields = ("user__username",)
    list_filter = ("timestamp",)


@admin.register(PrivateKeyAccessLog)
class PrivateKeyAccessLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "success", "ip_address", "timestamp")
    search_fields = ("user__username", "ip_address", "user_agent")
    list_filter = ("success", "action", "timestamp")
    readonly_fields = ("timestamp",)
