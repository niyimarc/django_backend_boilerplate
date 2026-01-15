from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Invitation, AccountAccess, ActivityLog
from django.utils import timezone

class InvitationSerializer(serializers.ModelSerializer):
    inviter = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Invitation
        fields = ['id', 'inviter', 'email', 'role', 'token', 'created_at', 'accepted']
        read_only_fields = ['token', 'created_at', 'accepted']


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.UUIDField()


class AccountAccessSerializer(serializers.ModelSerializer):
    owner_full_name = serializers.SerializerMethodField()
    collaborator_full_name = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = AccountAccess
        fields = [
            "id",
            "owner_full_name",
            "collaborator_full_name",
            "role",
            "status",
            "created_at",
        ]

    def get_owner_full_name(self, obj):
        return f"{obj.owner.first_name} {obj.owner.last_name}".strip()

    def get_collaborator_full_name(self, obj):
        return f"{obj.collaborator.first_name} {obj.collaborator.last_name}".strip()

    def get_created_at(self, obj):
        if obj.created_at:
            from django.utils import timezone
            return timezone.localtime(obj.created_at).strftime("%b %d, %Y, %I:%M %p")
        return None

class UpdateRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountAccess
        fields = ['role']

class ActivityLogSerializer(serializers.ModelSerializer):
    actor = serializers.StringRelatedField()
    owner = serializers.StringRelatedField()
    actor_email = serializers.EmailField(source="actor.email", read_only=True)
    actor_id = serializers.IntegerField(source="actor.id", read_only=True)
    model = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "actor", "actor_email", "actor_id", "owner", "action", "model", "object_id", "changes", "created_at"]

    def get_model(self, obj):
        return obj.content_type.model  # e.g. 'campaign'
    
    def get_created_at(self, obj):
        if obj.created_at:
            from django.utils import timezone
            return timezone.localtime(obj.created_at).strftime("%b %d, %Y, %I:%M %p")
        return None
