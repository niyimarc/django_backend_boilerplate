from datetime import timedelta
from django.utils import timezone
from .models import PrivateKeyAccessLog, KeyRegenerationLog

def too_many_failed_attempts(user, action=None, limit=5, window_minutes=15):
    # Check if a user has too many failed attempts within the given time window.
    cutoff = timezone.now() - timedelta(minutes=window_minutes)
    qs = PrivateKeyAccessLog.objects.filter(
        user=user, success=False, timestamp__gte=cutoff
    )
    if action:
        qs = qs.filter(action=action)

    return qs.count() >= limit

def too_many_regenerations(user, limit=3, period_hours=24):
    # Check if a user has exceeded the allowed number of key regenerations
    # within the given time period.
    since = timezone.now() - timedelta(hours=period_hours)
    logs = KeyRegenerationLog.objects.filter(
        user=user,
        timestamp__gte=since
    ).order_by("timestamp")

    regen_count = logs.count()

    if regen_count >= limit:
        # Find when the first regeneration in this window will expire
        earliest_log = logs.first()
        next_allowed_time = earliest_log.timestamp + timedelta(hours=period_hours)
        remaining = next_allowed_time - timezone.now()

        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)

        cooldown_message = (
            f"You have reached the regeneration limit. "
            f"Please try again in {hours}h {minutes}m."
        )
        return True, cooldown_message

    return False, None
