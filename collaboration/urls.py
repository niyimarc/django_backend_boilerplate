# collaboration/urls.py
from django.urls import path
from .views import (
    InviteUserView,
    AcceptInvitationView,
    AccountCollaboratorsView,
    MyAccessibleAccountsView,
    RemoveCollaboratorView,
    UpdateCollaboratorRoleView,
    ActivityFeedView
)

urlpatterns = [
    path('api/invitation/invite/', InviteUserView.as_view()),
    path('api/invitation/accept/', AcceptInvitationView.as_view()),
    path('api/collaborators/', AccountCollaboratorsView.as_view()),
    path('api/accessible_accounts/', MyAccessibleAccountsView.as_view()),
    path('api/remove/<int:pk>/', RemoveCollaboratorView.as_view()),
    path('api/update_role/<int:pk>/', UpdateCollaboratorRoleView.as_view()),
    path('api/activity/', ActivityFeedView.as_view()),
]