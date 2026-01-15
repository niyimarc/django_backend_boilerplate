from rest_framework import authentication, exceptions
from .models import UserKeyPair

class PublicKeyAuthentication(authentication.BaseAuthentication):
    """
    Authenticate using public key derived from user's private key.
    """
    def authenticate(self, request):
        public_key = request.headers.get('X-PUBLIC-KEY')
        if not public_key:
            return None

        try:
            key_pair = UserKeyPair.objects.get(revoked=False)
        except UserKeyPair.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid or revoked public key.")

        if public_key != key_pair.public_key:
            raise exceptions.AuthenticationFailed("Invalid or outdated public key.")

        return (key_pair.user, None)
