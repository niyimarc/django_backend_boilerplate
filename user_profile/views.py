from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, generics
from django.contrib.auth.models import User
from django.utils.http import urlsafe_base64_decode
from .serializers import BillingAddressSerializer
from .models import BillingAddress, Profile
from .signals import send_password_reset_email
from auth_core.views import PrivateUserViewMixin, PublicViewMixin

# Create your views here.
class UserProfileView(PrivateUserViewMixin, APIView):
    def get(self, request):
        user = request.user
        billing = getattr(user, 'billing_address', None)

        billing_data = None
        if billing:
            billing_data = {
                "address": billing.address,
                "state": billing.state,
                "city": billing.city,
                "apartment": billing.apartment,
                "country": billing.country,
                "zip_code": billing.zip_code,
                "is_verified": billing.is_verified,
            }

        return Response({
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "billing_address": billing_data
        })

class RequestPasswordResetView(PublicViewMixin, generics.GenericAPIView):
    """
    POST /api/user/request_password_reset/
    Body: { "email": "<user@example.com>" }

    Sends a password reset link to the user's registered email.
    """

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")

        if not email:
            return Response(
                {"error": "Email address is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
            profile = user.profile
        except User.DoesNotExist:
            # For security, don't reveal whether the email exists
            return Response(
                {"message": "If an account exists, a reset link has been sent."},
                status=status.HTTP_200_OK,
            )

        # Generate token and send reset email
        token = profile.generate_password_reset_token()
        send_password_reset_email(user, profile, token)

        return Response(
            {"message": "If an account exists, a reset link has been sent."},
            status=status.HTTP_200_OK,
        )
    
class VerifyEmailView(PublicViewMixin, generics.GenericAPIView):
    """
    POST /api/user/verify_email/
    Body: { "token": "<token>" }
    Public endpoint that verifies a user's email using the token sent via email.
    """

    def post(self, request, *args, **kwargs):
        token = request.data.get("token")

        if not token:
            return Response(
                {"error": "Missing verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = Profile.objects.get(verification_token=token)
        except Profile.DoesNotExist:
            return Response(
                {"error": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if profile.email_verified:
            return Response(
                {"message": "Email already verified."},
                status=status.HTTP_200_OK,
            )

        # Mark as verified
        profile.email_verified = True
        profile.is_verified = True
        profile.save()

        return Response(
            {"message": "Email verified successfully."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(PublicViewMixin, generics.GenericAPIView):
    """
    POST /api/user/reset_password/
    Body:
    {
        "uidb64": "<uidb64>",
        "token": "<token>",
        "new_password": "StrongPassword123"
    }
    Public endpoint for resetting user password after verification link.
    """

    def post(self, request, *args, **kwargs):
        uidb64 = request.data.get("uidb64")
        token = request.data.get("token")
        new_password = request.data.get("new_password")

        if not all([uidb64, token, new_password]):
            return Response(
                {"error": "Missing one or more required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Decode user ID from base64
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
            profile = user.profile
        except Exception:
            return Response(
                {"error": "Invalid or malformed reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate token
        if not profile.is_password_reset_token_valid() or str(profile.password_reset_token) != token:
            return Response(
                {"error": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update password
        user.set_password(new_password)
        user.save()

        profile.password_reset_token_is_used = True
        profile.save()

        return Response(
            {"message": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )
     
class BillingAddressView(PrivateUserViewMixin, APIView):
    def post(self, request):
        user = request.user
        serializer = BillingAddressSerializer(data=request.data)

        if serializer.is_valid():
            validated_data = serializer.validated_data
            validated_data["is_verified"] = True 
            # Update if already exists, or create new
            billing_address, created = BillingAddress.objects.update_or_create(
                user=user,
                defaults=validated_data
            )
            return Response({
                "success": True,
                "created": created,
                "billing_address": BillingAddressSerializer(billing_address).data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)