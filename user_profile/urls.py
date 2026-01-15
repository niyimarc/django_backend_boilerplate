from django.urls import path
from .views import (
                    UserProfileView,
                    BillingAddressView,
                    VerifyEmailView,
                    ResetPasswordView,
                    RequestPasswordResetView
                    )

app_name = 'user_profile'

urlpatterns = [
    path('api/user/profile/', UserProfileView.as_view(), name="profile"),
    path('api/user/billing_address/', BillingAddressView.as_view(), name="billing_address"),
    path("api/user/verify_email/", VerifyEmailView.as_view()),
    path("api/user/request_password_reset/", RequestPasswordResetView.as_view()),
    path("api/user/reset_password/", ResetPasswordView.as_view()),
]