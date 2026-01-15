# collaboration/services/access_control.py
from collaboration.models import AccountAccess
from collaboration.constants import ROLE_HIERARCHY

def expand_roles(roles):
    expanded = set()
    for role in roles:
        expanded.update(ROLE_HIERARCHY.get(role, []))
    return list(expanded)

def has_account_access(user, owner, roles=None, obj=None):
    """
    Check if user has required role on owner's account
    or specific object (scoped_ids).
    """
    roles = expand_roles(roles or [])

    # Owner always has access
    if user == owner:
        return True

    if not roles:
        return False

    try:
        access = AccountAccess.objects.get(owner=owner, collaborator=user)
    except AccountAccess.DoesNotExist:
        return False

    # Role check
    if access.role not in roles:
        return False

    # Global access
    if not access.scoped_ids:
        return True

    # Scoped access
    if obj:
        # obj must declare its type (e.g., model name)
        obj_type = obj.__class__.__name__.lower()  
        if access.scope_type == obj_type and obj.id in access.scoped_ids:
            return True

    return False
