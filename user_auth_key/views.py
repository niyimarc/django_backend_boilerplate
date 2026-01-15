from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import UserKeyPair, PrivateKeyAccessLog
from .serializers import UserKeyPairSerializer
from auth_core.views import PrivateUserViewMixin
from .utils import too_many_failed_attempts, too_many_regenerations

class UserKeyPairView(PrivateUserViewMixin, generics.RetrieveAPIView):
    serializer_class = UserKeyPairSerializer

    def get_object(self):
        obj, _ = UserKeyPair.objects.get_or_create(user=self.request.user)
        return obj

class UserKeyPairRegenerateView(PrivateUserViewMixin, APIView):
    def post(self, request):
        password = request.data.get("password")
        user = request.user
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Check rate limit
        if too_many_failed_attempts(user, action="regenerate_key"):
            return Response(
                {"error": "Too many failed attempts. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        if not password:
            PrivateKeyAccessLog.objects.create(
                user=user, 
                success=False, 
                ip_address=ip_address, 
                user_agent=user_agent,
                action="regenerate_key"
            )
            return Response(
                {"error": "Password is required to regenerate the private key."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(password):
            PrivateKeyAccessLog.objects.create(
                user=user, 
                success=False, 
                ip_address=ip_address, 
                user_agent=user_agent,
                action="regenerate_key"
            )
            return Response(
                {"error": "Invalid password."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Success case
        key_pair = get_object_or_404(UserKeyPair, user=user)
        new_public_key = key_pair.regenerate_keys()
        PrivateKeyAccessLog.objects.create(
            user=user, 
            success=True, 
            ip_address=ip_address, 
            user_agent=user_agent,
            action="regenerate_key"
        )

        serializer = UserKeyPairSerializer(key_pair)
        data = serializer.data
        data['public_key'] = new_public_key
        return Response(data)


class UserKeyPairShowPrivateKeyView(PrivateUserViewMixin, APIView):
    def post(self, request):
        password = request.data.get("password")
        user = request.user
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Check rate limit
        if too_many_failed_attempts(user, action="show_private_key"):
            return Response(
                {"error": "Too many failed attempts. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        if not password:
            PrivateKeyAccessLog.objects.create(
                user=user, 
                success=False, 
                ip_address=ip_address, 
                user_agent=user_agent,
                action="show_private_key"
            )
            return Response(
                {"error": "Password is required to view the private key."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(password):
            PrivateKeyAccessLog.objects.create(
                user=user, 
                success=False, 
                ip_address=ip_address, 
                user_agent=user_agent,
                action="show_private_key"
            )
            return Response(
                {"error": "Invalid password."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check regeneration frequency
        exceeded, cooldown_message = too_many_regenerations(user)
        if exceeded:
            return Response(
                {"error": cooldown_message},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # Success case
        key_pair = get_object_or_404(UserKeyPair, user=user)
        PrivateKeyAccessLog.objects.create(
            user=user, 
            success=True, 
            ip_address=ip_address, 
            user_agent=user_agent,
            action="show_private_key"
        )

        return Response({"private_key": key_pair.show_private_key()})