from django.urls import path
from .views import (
    UserKeyPairView,
    UserKeyPairRegenerateView,
    UserKeyPairShowPrivateKeyView,
)

urlpatterns = [
    path("api/key_pair/", UserKeyPairView.as_view(),),
    path("api/key_pair/regenerate/", UserKeyPairRegenerateView.as_view()),
    path("api/key_pair/show_private_key/", UserKeyPairShowPrivateKeyView.as_view()),
]
