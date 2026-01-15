from rest_framework.permissions import BasePermission
from .services.access_control import has_account_access

class BaseAccessPermission(BasePermission):
    allowed_roles = []

    def has_permission(self, request, view):
        if hasattr(view, "get_object"):  # object-based view
            return True  # defer to has_object_permission

        owner_id = view.kwargs.get("owner_id")
        if owner_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                owner = User.objects.get(pk=owner_id)
            except User.DoesNotExist:
                return False
            return has_account_access(request.user, owner, roles=self.allowed_roles)

        return False

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "owner", None)
        if not owner:
            return False
        return has_account_access(request.user, owner, roles=self.allowed_roles, obj=obj)

class IsOwner(BaseAccessPermission):
    allowed_roles = []  # Only owner, no collaborators

class IsViewer(BaseAccessPermission):
    allowed_roles = ["viewer"]  # viewer → editor → admin

class IsEditor(BaseAccessPermission):
    allowed_roles = ["editor"]  # editor → admin

class IsAdmin(BaseAccessPermission):
    allowed_roles = ["admin"]  # admin only