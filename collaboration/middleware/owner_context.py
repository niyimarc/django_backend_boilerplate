from django.contrib.auth.models import User
from collaboration.models import AccountAccess
from django.core.exceptions import ObjectDoesNotExist

class OwnerContextMiddleware:
    """
    Middleware that sets request.owner_context for any authenticated request.
    Supports X-Owner-Context as either a User ID or an AccountAccess ID.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.owner_context = None

        owner_id = (
            request.headers.get("X-Owner-Context")
            or request.META.get("HTTP_X_OWNER_CONTEXT")
        )
        # print(f"[Middleware] Incoming X-Owner-Context: {owner_id}")

        if not owner_id:
            owner_id = (
                request.session.get("active_account_id")
                or request.session.get("owner_id")
            )
            # if owner_id:
            #     print(f"[Middleware] Found owner_id in session: {owner_id}")

        resolved_owner = None
        if owner_id:
            try:
                # Try direct User lookup
                resolved_owner = User.objects.get(pk=int(owner_id))
                # print(f"[Middleware] Resolved as User ID {owner_id}")
            except ObjectDoesNotExist:
                try:
                    # Fallback: interpret as AccountAccess
                    account_access = AccountAccess.objects.get(pk=int(owner_id))
                    resolved_owner = account_access.owner
                    # print(f"[Middleware] Resolved via AccountAccess → {resolved_owner} (User ID: {resolved_owner.id})")
                except ObjectDoesNotExist:
                    print(f"[Middleware] No matching User or AccountAccess for ID {owner_id}")
                except (ValueError, TypeError):
                    print(f"[Middleware] Invalid AccountAccess ID format: {owner_id}")
            except (ValueError, TypeError):
                print(f"[Middleware] Invalid User ID format: {owner_id}")

        if resolved_owner:
            request.owner_context = resolved_owner
        elif request.user.is_authenticated:
            request.owner_context = request.user
            # print(f"[Middleware] Defaulted to request.user ({request.user})")

        return self.get_response(request)