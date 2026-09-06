from __future__ import annotations

from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone


class LastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = timezone.now()
            last_activity = request.session.get("last_activity")
            if last_activity:
                last_activity_dt = timezone.datetime.fromisoformat(last_activity)
                if timezone.is_naive(last_activity_dt):
                    last_activity_dt = timezone.make_aware(last_activity_dt, timezone.get_current_timezone())
                idle_minutes = (now - last_activity_dt).total_seconds() / 60
                if idle_minutes > settings.SESSION_IDLE_TIMEOUT_MINUTES:
                    logout(request)
            request.session["last_activity"] = now.isoformat()
        response = self.get_response(request)
        return response

