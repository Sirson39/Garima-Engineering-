from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import LoginAttempt


class LoginAttemptTests(TestCase):
    def test_register_failure_locks_account_after_threshold(self):
        attempt, _ = LoginAttempt.objects.get_or_create(identifier="demo", ip_address="127.0.0.1")
        attempt.register_failure(limit=2, window_minutes=10)
        self.assertFalse(attempt.is_locked())
        attempt.register_failure(limit=2, window_minutes=10)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_locked())
        self.assertIsNotNone(attempt.locked_until)

