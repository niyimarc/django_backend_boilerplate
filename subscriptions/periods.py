from django.utils import timezone
from datetime import timedelta

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    relativedelta = None


def monthly_or_yearly(interval: str, start=None):
    """
    Period function for subscriptions.
    Supports 'monthly', 'yearly', 'weekly', 'daily', and fallbacks safely.
    """
    start = start or timezone.now()
    interval = (interval or "").lower().strip()  # normalize input

    if relativedelta:
        if interval in ("year", "yearly", "annual", "annually"):
            return start + relativedelta(years=1)
        elif interval in ("month", "monthly"):
            return start + relativedelta(months=1)
        elif interval in ("week", "weekly"):
            return start + timedelta(weeks=1)
        elif interval in ("day", "daily"):
            return start + timedelta(days=1)
        else:
            # print(f"[WARN] Unknown interval '{interval}', defaulting to +30 days.")
            return start + timedelta(days=30)

    # Fallback if python-dateutil isn't installed
    if interval in ("year", "yearly", "annual", "annually"):
        return start + timedelta(days=365)
    elif interval in ("month", "monthly"):
        return start + timedelta(days=30)
    elif interval in ("week", "weekly"):
        return start + timedelta(weeks=1)
    elif interval in ("day", "daily"):
        return start + timedelta(days=1)
    else:
        # print(f"[WARN] Unknown interval '{interval}', defaulting to +30 days.")
        return start + timedelta(days=30)
