import hmac
import hashlib
import time
from rest_framework import authentication, exceptions
from .models import UserKeyPair

class UserAuthKeyHMACAuthentication(authentication.BaseAuthentication):
    """
    Authenticate external requests using:
    - X-PUBLIC-KEY header
    - X-TIMESTAMP header
    - X-SIGNATURE header (HMAC-SHA256 of timestamp + body using private key)
    """
    TIMEOUT = 300  # 5 minutes

    def authenticate(self, request):
        public_key = request.headers.get("X-PUBLIC-KEY")
        timestamp = request.headers.get("X-TIMESTAMP")
        signature = request.headers.get("X-SIGNATURE")

        if not all([public_key, timestamp, signature]):
            raise exceptions.AuthenticationFailed("Missing required headers")

        # Validate timestamp (prevent replay attacks)
        try:
            ts = int(timestamp)
        except ValueError:
            raise exceptions.AuthenticationFailed("Invalid timestamp")
        
        now = int(time.time())
        if abs(now - ts) > self.TIMEOUT:
            raise exceptions.AuthenticationFailed("Request expired")

        # Find the user by derived public key
        try:
            key_pair = UserKeyPair.objects.get(revoked=False)
        except UserKeyPair.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid public key")

        if key_pair.public_key != public_key:
            raise exceptions.AuthenticationFailed("Invalid public key")

        # Compute expected HMAC signature
        body = request.body or b""
        message = f"{timestamp}:{body.decode()}".encode()
        expected_signature = hmac.new(
            key_pair.private_key.encode(),
            message,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            raise exceptions.AuthenticationFailed("Invalid signature")

        return (key_pair.user, None)
