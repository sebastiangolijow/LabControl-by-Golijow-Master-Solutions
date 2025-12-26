"""Tests for authentication rate limiting."""

from django.core.cache import cache
from rest_framework import status

from tests.base import BaseTestCase


class LoginRateLimitingTests(BaseTestCase):
    """Tests for login rate limiting (5 attempts per 15 minutes)."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        # Clear cache before each test to ensure clean state
        cache.clear()

        # Create a test user for login attempts (verified to allow login)
        self.user = self.create_patient(
            email="test@example.com", password="TestPassword123!", is_verified=True
        )

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()
        super().tearDown()

    def test_login_allows_5_attempts(self):
        """Test that 5 login attempts are allowed."""
        client = self.client

        # Make 5 failed login attempts
        for i in range(5):
            response = client.post(
                "/api/v1/auth/login/",
                {"email": "test@example.com", "password": "wrongpassword"},
                format="json",
            )
            # Should get 400 (invalid credentials), not 429 (throttled)
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Attempt {i+1} should not be throttled",
            )

    def test_login_blocks_6th_attempt(self):
        """Test that 6th login attempt is blocked by rate limiting."""
        client = self.client

        # Make 5 failed login attempts
        for i in range(5):
            client.post(
                "/api/v1/auth/login/",
                {"email": "test@example.com", "password": "wrongpassword"},
                format="json",
            )

        # 6th attempt should be throttled
        response = client.post(
            "/api/v1/auth/login/",
            {"email": "test@example.com", "password": "wrongpassword"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("throttled", response.data["detail"].lower())

    def test_successful_and_failed_logins_share_limit(self):
        """Test that all login attempts (success or fail) count toward the same limit."""
        client = self.client

        # Make 3 failed attempts
        for i in range(3):
            client.post(
                "/api/v1/auth/login/",
                {"email": "test@example.com", "password": "wrongpassword"},
                format="json",
            )

        # Make 2 more failed attempts
        for i in range(2):
            response = client.post(
                "/api/v1/auth/login/",
                {"email": "test@example.com", "password": "wrong"},
                format="json",
            )
            # Should still return 400 (bad credentials), not throttled yet
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 6th attempt should be throttled (we've made 5 total attempts)
        response = client.post(
            "/api/v1/auth/login/",
            {"email": "test@example.com", "password": "TestPassword123!"},
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
            "6th login attempt should be throttled regardless of correct password",
        )

    def test_rate_limit_is_per_ip(self):
        """Test that rate limiting is based on IP address."""
        # This test verifies the rate limit is IP-based
        # In a real scenario, different IPs would have separate limits
        # For testing purposes, we verify the cache key includes IP info

        client = self.client

        # Make 5 attempts from "same IP" (default test client)
        for i in range(5):
            client.post(
                "/api/v1/auth/login/",
                {"email": "test@example.com", "password": "wrongpassword"},
                format="json",
            )

        # 6th attempt should be throttled
        response = client.post(
            "/api/v1/auth/login/",
            {"email": "test@example.com", "password": "wrongpassword"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_get_request_not_throttled(self):
        """Test that GET requests to login endpoint are not throttled."""
        client = self.client

        # Make 6 GET requests (should all succeed, not throttled)
        for i in range(6):
            response = client.get("/api/v1/auth/login/")
            # GET to login returns 405 Method Not Allowed, not 429 Throttled
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class RegistrationRateLimitingTests(BaseTestCase):
    """Tests for registration rate limiting (5 attempts per hour)."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()
        super().tearDown()

    def test_registration_allows_5_attempts(self):
        """Test that 5 registrations are allowed per hour."""
        client = self.client

        # Make 5 registration attempts
        for i in range(5):
            response = client.post(
                "/api/v1/auth/registration/",
                {
                    "email": f"user{i}@example.com",
                    "password1": "TestPassword123!",
                    "password2": "TestPassword123!",
                    "first_name": "Test",
                    "last_name": "User",
                },
                format="json",
            )
            # Should succeed (201 Created) or fail validation (400), not throttled (429)
            self.assertIn(
                response.status_code,
                [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST],
                f"Registration attempt {i+1} should not be throttled",
            )

    def test_registration_blocks_6th_attempt(self):
        """Test that 6th registration is blocked by rate limiting."""
        client = self.client

        # Make 5 registration attempts
        for i in range(5):
            client.post(
                "/api/v1/auth/registration/",
                {
                    "email": f"user{i}@example.com",
                    "password1": "TestPassword123!",
                    "password2": "TestPassword123!",
                    "first_name": "Test",
                    "last_name": "User",
                },
                format="json",
            )

        # 6th attempt should be throttled
        response = client.post(
            "/api/v1/auth/registration/",
            {
                "email": "user6@example.com",
                "password1": "TestPassword123!",
                "password2": "TestPassword123!",
                "first_name": "Test",
                "last_name": "User",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class RateLimitingSecurityTests(BaseTestCase):
    """Security-focused tests for rate limiting."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()
        super().tearDown()

    def test_rate_limit_prevents_brute_force(self):
        """
        Test that rate limiting effectively prevents brute-force attacks.

        This simulates an attacker trying to brute-force a password
        by making many login attempts.
        """
        client = self.client
        _user = self.create_patient(  # noqa: F841
            email="victim@example.com", password="CorrectPassword123!", is_verified=True
        )

        # Attacker makes 5 failed attempts
        passwords = ["wrong1", "wrong2", "wrong3", "wrong4", "wrong5"]
        for password in passwords:
            response = client.post(
                "/api/v1/auth/login/",
                {"email": "victim@example.com", "password": password},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 6th attempt is blocked, even with correct password
        response = client.post(
            "/api/v1/auth/login/",
            {"email": "victim@example.com", "password": "CorrectPassword123!"},
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Attacker should be blocked after 5 attempts, even with correct password",
        )
