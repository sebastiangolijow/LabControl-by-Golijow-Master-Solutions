"""Tests for the /health/ liveness endpoint used by docker healthchecks."""

import json

from django.test import TestCase, override_settings
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_returns_200_with_status_ok(self):
        """The endpoint must return 200 + JSON {"status": "ok"} so docker
        healthchecks parse it correctly."""
        url = reverse("health")
        self.assertEqual(url, "/health/")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        body = json.loads(response.content)
        self.assertEqual(body, {"status": "ok"})

    def test_does_not_require_authentication(self):
        """Anonymous requests must succeed — the docker healthcheck doesn't
        carry credentials."""
        # No login, no JWT
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)

    def test_post_is_rejected(self):
        """Only GET is allowed."""
        response = self.client.post("/health/")
        self.assertEqual(response.status_code, 405)
