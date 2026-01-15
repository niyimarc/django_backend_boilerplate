from django.http import JsonResponse
import hmac, hashlib, time
from django.conf import settings
from django.urls import resolve
from urllib.parse import urlparse
from .models import APIKey

class HMACAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.secret_key = settings.HMAC_SECRET_KEY.encode()

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        try:
            EXEMPT_PATHS = [
                # "/connect/google/callback/",
                "/connect/meta/callback/",
                "/connect/tiktok/callback/",
            ]
            # Skip middleware for media and admin paths
            if (
                request.path.startswith('/media/') or
                resolve(request.path).app_name == 'admin' or
                request.path == '/api/token/refresh/' or
                request.path.startswith('/api/external/') or
                request.path.startswith('/webhooks/stripe/') or
                request.path in EXEMPT_PATHS
            ):
                return None
        except Exception:
            pass  # In case resolve fails, just continue to validation

        signature = request.headers.get('X-Signature')
        timestamp = request.headers.get('X-Timestamp')

        if not signature or not timestamp:
            return JsonResponse({"detail": "Missing signature or timestamp"}, status=403)

        # Reject old timestamps (prevent replay)
        if abs(int(time.time()) - int(timestamp)) > 60:
            return JsonResponse({"detail": "Request expired"}, status=403)

        message = f"{timestamp}:{request.get_full_path()}"
        
        expected_signature = hmac.new(
            self.secret_key,
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            return JsonResponse({"detail": "Invalid signature"}, status=403)

        return None

class ApplicationBaseURLValidatorMiddleware:
    """
    Ensure that if an Application has a base_url configured,
    the incoming request must originate from that same base_url.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        try:
            if request.path.startswith("/api/external/"):
                return None
        except Exception:
            pass

        api_key = request.headers.get("X-API-KEY")
        if not api_key:
            return None  # already enforced by APIKeyAuthentication

        try:
            application = APIKey.objects.select_related("application").get(key=api_key, is_active=True).application
        except APIKey.DoesNotExist:
            return JsonResponse({"detail": "Invalid API key"}, status=403)

        # If application has no base_url → skip (non-web app, like mobile)
        if not application.base_url:
            request.application = application
            return None

        # Check request Origin or Referer header
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        # print(f"Origin: {origin}")
        if not origin:
            return JsonResponse({"detail": "Missing Origin/Referer header for web-based app."}, status=403)

        # Parse host from both
        app_host = urlparse(application.base_url).netloc
        req_host = urlparse(origin).netloc
        # print(f"App Host: {app_host}")
        # print(f"Request Host: {req_host}")
        if app_host != req_host:
            return JsonResponse(
                {"detail": f"Invalid base_url. Expected {application.base_url}, got {origin}"},
                status=403
            )

        request.application = application
        return None
