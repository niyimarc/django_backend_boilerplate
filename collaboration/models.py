from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from .constants import ROLE_CHOICES, ACCESS_STATUS_CHOICES

class Invitation(models.Model):
    inviter = models.ForeignKey(User, related_name="sent_invitations", on_delete=models.CASCADE)
    email = models.EmailField()  # who is being invited
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    accepted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} invited by {self.inviter.username} as {self.role}"

class AccountAccess(models.Model):
    owner = models.ForeignKey(User, related_name="account_owners", on_delete=models.CASCADE)
    collaborator = models.ForeignKey(User, related_name="account_collaborations", on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    # Generic scope definition
    scope_type = models.CharField(max_length=50, blank=True, null=True)  
    scoped_ids = models.JSONField(default=list, blank=True)

    status = models.CharField(
        max_length=10,
        choices=ACCESS_STATUS_CHOICES,
        default="active"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("owner", "collaborator")

    def __str__(self):
        scope_info = (
            f"{self.scope_type}s {self.scoped_ids}"
            if self.scoped_ids else "global access"
        )
        return f"{self.collaborator.username} ({self.role}, {self.status}) on {self.owner.username}'s {scope_info}"
    
    @classmethod
    def has_access(cls, user, owner, roles=None, obj=None):
        from collaboration.services.access_control import has_account_access
        return has_account_access(user, owner, roles=roles, obj=obj)
    
class ActivityLog(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_logs")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="performed_actions")
    action = models.CharField(max_length=255)

    # Generic link to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    changes = models.JSONField(null=True, blank=True)  # e.g., {"budget": ["100", "200"]}
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        actor = self.actor.username if self.actor else "System"
        return f"{actor} {self.action} on {self.content_type} #{self.object_id}"