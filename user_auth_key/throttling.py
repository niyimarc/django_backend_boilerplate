from rest_framework.throttling import BaseThrottle
from rest_framework.exceptions import Throttled
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from .models import UserKeyPair

class ExternalPlatformRateThrottle(BaseThrottle):
    """
    Rate limit per public key for external platform requests.
    """
    cache_format = 'throttle_public_key_{key}'

    def __init__(self, rate_limit=100, rate_period=timedelta(minutes=1)):
        self.rate_limit = rate_limit
        self.rate_period = rate_period
        self._retry_after = None

    def get_cache_key(self, request):
        public_key = request.headers.get("X-PUBLIC-KEY")
        if not public_key:
            return None
        return self.cache_format.format(key=public_key)

    def allow_request(self, request, view):
        cache_key = self.get_cache_key(request)
        if not cache_key:
            return False

        history = cache.get(cache_key, [])
        now = timezone.now()
        window_start = now - self.rate_period
        history = [ts for ts in history if ts > window_start]

        if len(history) >= self.rate_limit:
            # Rate limit exceeded
            self._retry_after = (history[0] + self.rate_period - now).total_seconds()
            return False

        # Add current request
        history.append(now)
        cache.set(cache_key, history, timeout=int(self.rate_period.total_seconds()))
        self._retry_after = None
        return True

    def wait(self):
        return self._retry_after


class IPBlacklistThrottle(BaseThrottle):
    """
    Temporarily blacklist an IP if it repeatedly violates the rate limit.
    """
    blacklist_cache_prefix = 'blacklisted_ip_'
    blacklist_threshold = 5  # Number of violations to trigger temporary blacklist
    blacklist_duration = timedelta(hours=1)  # Duration of temporary blacklist

    def allow_request(self, request, view):
        ip = self.get_ident(request)
        if cache.get(self.blacklist_cache_prefix + ip):
            raise Throttled(detail="Your IP has been temporarily blocked due to repeated violations.")

        return True

    def record_violation(self, request):
        ip = self.get_ident(request)
        key = f"violation_count_{ip}"
        count = cache.get(key, 0) + 1
        cache.set(key, count, timeout=int(self.blacklist_duration.total_seconds()))

        if count >= self.blacklist_threshold:
            cache.set(self.blacklist_cache_prefix + ip, True, timeout=int(self.blacklist_duration.total_seconds()))
