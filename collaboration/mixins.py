from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from .models import ActivityLog
from rest_framework.exceptions import PermissionDenied
from collaboration.services.access_control import has_account_access

class TrackableModelMixin:
    """
    Optional mixin for explicit logging of actions.
    Add to any model with a `user` (owner) field.
    """

    def log_action(self, actor, action, changes=None):
        """Manual action logging (no save required)."""
        ActivityLog.objects.create(
            owner=self.owner,
            actor=actor,
            action=action,
            content_type=ContentType.objects.get_for_model(self.__class__),
            object_id=self.pk,
            changes=changes or {},
        )

    def save_with_tracking(self, actor, *args, **kwargs):
        """Call this instead of .save() to track changes explicitly."""
        if not self.pk:
            super().save(*args, **kwargs)
            self.log_action(actor, "created")
            return

        # Compute changes (diff)
        old_instance = self.__class__.objects.get(pk=self.pk)
        diff = {}
        for field in self._meta.fields:
            name = field.name
            old_val = getattr(old_instance, name)
            new_val = getattr(self, name)
            if old_val != new_val:
                diff[name] = [old_val, new_val]

        super().save(*args, **kwargs)
        if diff:
            self.log_action(actor, "updated", changes=diff)

class OwnerContextMixin:
    """
    Provides automatic account context and access validation.
    Ensures collaborators can only act on objects owned by
    their permitted account.
    """

    required_roles = ["editor", "admin"]  # Default allowed roles

    def get_owner_context(self, request):
        """
        Returns the effective owner for this request.
        Priority:
          1. Middleware-set `request.owner_context`
          2. Fallback to `request.user`
        """
        user = request.user
        owner = getattr(request, "owner_context", None) or user

        # Validate collaborator permissions
        if owner != user:
            if not has_account_access(user, owner, roles=self.required_roles):
                raise PermissionDenied("You don't have permission to act on behalf of this account.")

        return owner

    def check_object_belongs_to_owner(self, obj, owner):
        """
        Ensures that the object being accessed belongs to the current owner context.
        """
        obj_owner = getattr(obj, "owner", None)
        if not obj_owner:
            raise PermissionDenied("This object has no owner associated.")
        if obj_owner != owner:
            raise PermissionDenied("This object does not belong to the selected account context.")

    def get_and_validate_object(self):
        """
        Retrieves the object and ensures it belongs to the correct owner context.
        """
        obj = self.get_object()
        owner = self.get_owner_context(self.request)
        self.check_object_belongs_to_owner(obj, owner)
        return obj