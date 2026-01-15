from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .models import Invitation, AccountAccess, ActivityLog
from auth_core.views import PrivateUserViewMixin
from .utils.email_utils import send_invitation_email
from .serializers import (
    InvitationSerializer,
    AcceptInvitationSerializer,
    AccountAccessSerializer,
    UpdateRoleSerializer,
    ActivityLogSerializer,
)

# Invite someone
class InviteUserView(PrivateUserViewMixin, generics.CreateAPIView):
    serializer_class = InvitationSerializer
    
    def perform_create(self, serializer):
        inviter=self.request.user
        invitation = serializer.save(inviter=inviter)
        send_invitation_email(invitation)

# Accept an invite
class AcceptInvitationView(PrivateUserViewMixin, generics.GenericAPIView):
    serializer_class = AcceptInvitationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        # print(f"Token: {token}")
        invitation = get_object_or_404(Invitation, token=token, accepted=False)
        # print(invitation)
        # print(request.user.email.lower())
        # print(invitation.email.lower())
        # Ensure that the logged-in user's email matches the invited email
        if request.user.email.lower() != invitation.email.lower():
            raise PermissionDenied(
                "This invitation was sent to a different email address. "
                "Please log in with the correct account."
            )
        
        # Link invited user to inviter’s account
        AccountAccess.objects.get_or_create(
            owner=invitation.inviter,
            collaborator=request.user,
            defaults={'role': invitation.role}
        )

        invitation.accepted = True
        invitation.save()

        return Response({"message": "Invitation accepted successfully!"}, status=status.HTTP_200_OK)

# List collaborators for current user’s account
class AccountCollaboratorsView(PrivateUserViewMixin, generics.ListAPIView):
    serializer_class = AccountAccessSerializer

    def get_queryset(self):
        return AccountAccess.objects.filter(owner=self.request.user)

class MyAccessibleAccountsView(PrivateUserViewMixin, generics.ListAPIView):
    """
    Lists all accounts the current user can access:
    - Accounts they collaborate on
    - Their own account (as owner)
    Used for account switching in the frontend.
    """
    serializer_class = AccountAccessSerializer

    def get_queryset(self):
        user = self.request.user

        # All accounts where user is a collaborator
        collaborator_access = AccountAccess.objects.filter(collaborator=user)

        # Create a "virtual" access record for their own account (if not already added)
        own_access, _ = AccountAccess.objects.get_or_create(
            owner=user,
            collaborator=user,
            defaults={"role": "owner", "status": "active"},
        )

        # Combine their own account with other accessible accounts
        return (
            AccountAccess.objects.filter(
                id__in=[own_access.id] + list(collaborator_access.values_list("id", flat=True))
            )
            .select_related("owner")
            .order_by("owner__first_name", "owner__last_name")
        )

# Remove a collaborator
class RemoveCollaboratorView(PrivateUserViewMixin, generics.DestroyAPIView):
    serializer_class = AccountAccessSerializer

    def get_queryset(self):
        return AccountAccess.objects.filter(owner=self.request.user)

class UpdateCollaboratorRoleView(PrivateUserViewMixin, generics.UpdateAPIView):
    serializer_class = UpdateRoleSerializer

    def get_queryset(self):
        # Only allow owners to change roles of their collaborators
        return AccountAccess.objects.filter(owner=self.request.user)

class ActivityFeedView(PrivateUserViewMixin, generics.ListAPIView):
    """
    Returns all activities related to the current user's account.
    Includes actions by collaborators.
    """
    serializer_class = ActivityLogSerializer

    def get_queryset(self):
        # Show logs for the authenticated user's account
        return ActivityLog.objects.filter(owner=self.request.user).select_related("actor", "content_type")
