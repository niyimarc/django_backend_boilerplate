from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import AuthenticationFailed
from .authentication import PublicKeyAuthentication
from .middleware import UserAuthKeyHMACAuthentication
from .throttling import ExternalPlatformRateThrottle

class ExternalPlatformPrivateUserViewMixin(APIView):
    """
    Mixin for endpoints accessed by external platforms.
    Combines:
      - Public key check
      - HMAC verification using user's private key
      - Throttling per public key
    """

    authentication_classes = [PublicKeyAuthentication, UserAuthKeyHMACAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ExternalPlatformRateThrottle]

    def dispatch(self, *args, **kwargs):
        # Ensure public key exists
        public_key = self.request.headers.get("X-PUBLIC-KEY")
        if not public_key:
            return Response({"detail": "Public key missing."}, status=403)

        # Authenticate using both authentication classes
        user = None
        for auth_class in self.authentication_classes:
            try:
                user_auth_result = auth_class().authenticate(self.request)
                if user_auth_result:
                    user, _ = user_auth_result
            except AuthenticationFailed as e:
                return Response({"detail": str(e)}, status=403)

        if not user:
            return Response({"detail": "Authentication failed."}, status=403)

        self.request.user = user
        return super().dispatch(*args, **kwargs)
