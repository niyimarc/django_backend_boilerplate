from django.urls import path
from .external_views import (
                    ExternalUserProfileView,
                    ExternalBillingAddressView
                    )

urlpatterns = [
    path('api/user/profile/', ExternalUserProfileView.as_view(), name="profile"),
    path('api/billing_address/', ExternalBillingAddressView.as_view(), name="billing_address"),
]