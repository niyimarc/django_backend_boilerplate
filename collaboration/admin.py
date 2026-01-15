from django.contrib import admin
from .models import Invitation, AccountAccess, ActivityLog

@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "inviter", "role", "accepted", "created_at")
    list_filter = ("role", "accepted", "created_at")
    search_fields = ("email", "inviter__username")
    ordering = ("-created_at",)
    readonly_fields = ("token", "created_at")

    fieldsets = (
        ("Invitation Info", {
            "fields": ("inviter", "email", "role", "accepted")
        }),
        ("Metadata", {
            "fields": ("token", "created_at"),
            "classes": ("collapse",)
        }),
    )

@admin.register(AccountAccess)
class AccountAccessAdmin(admin.ModelAdmin):
    list_display = ("owner", "collaborator", "role", "scope_type", "created_at", "updated_at")
    list_filter = ("role", "scope_type", "created_at")
    search_fields = (
        "owner__username",
        "collaborator__username",
        "scope_type",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Account Access", {
            "fields": ("owner", "collaborator", "role")
        }),
        ("Scope Details", {
            "fields": ("scope_type", "scoped_ids"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "owner",
        "actor",
        "action",
        "content_type",
        "object_id",
        "created_at",
    )
    list_filter = ("content_type", "created_at")
    search_fields = (
        "owner__username",
        "actor__username",
        "action",
        "object_id",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "owner",
        "actor",
        "action",
        "content_type",
        "object_id",
        "changes",
        "created_at",
    )

    fieldsets = (
        ("Activity Info", {
            "fields": ("owner", "actor", "action")
        }),
        ("Linked Object", {
            "fields": ("content_type", "object_id", "changes")
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

    def has_add_permission(self, request):
        """Disallow manual creation of ActivityLog records."""
        return False