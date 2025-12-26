"""Tests for email verification functionality."""

from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone
from rest_framework import status

from apps.users.models import User
from tests.base import BaseTestCase


class EmailVerificationTests(BaseTestCase):
    """Test email verification workflow."""

    def test_patient_registration_sends_verification_email(self):
        """Test that registering a patient sends a verification email."""
        registration_data = {
            "email": "newuser@test.com",
            "password": "securepassword123",
            "password_confirm": "securepassword123",
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+1234567890",
            "lab_client_id": 1,
        }

        # Mock the Celery task to run synchronously
        with patch(
            "apps.notifications.tasks.send_verification_email.delay"
        ) as mock_task:
            # Make task execute immediately instead of async
            mock_task.side_effect = lambda user_id: self._send_verification_email_sync(
                user_id
            )

            response = self.client.post(
                "/api/v1/users/register/", registration_data, format="json"
            )

            assert response.status_code == status.HTTP_201_CREATED
            assert (
                "Please check your email to verify your account"
                in response.data["message"]
            )

            # Verify user was created but not verified
            user = User.objects.get(email="newuser@test.com")
            assert user.is_verified is False
            assert user.verification_token is not None
            assert user.verification_token_created_at is not None

            # Verify Celery task was called
            mock_task.assert_called_once_with(user.id)

    def test_verify_email_with_valid_token(self):
        """Test successful email verification with valid token."""
        # Create unverified user
        user = self.create_patient(email="test@test.com")
        user.is_verified = False
        token = user.generate_verification_token()

        # Verify email
        verification_data = {"email": user.email, "token": token}

        response = self.client.post(
            "/api/v1/users/verify-email/", verification_data, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "Email verified successfully" in response.data["message"]

        # Verify user is now verified
        user.refresh_from_db()
        assert user.is_verified is True
        assert user.verification_token is None
        assert user.verification_token_created_at is None

    def test_verify_email_with_invalid_token(self):
        """Test email verification fails with invalid token."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = False
        user.generate_verification_token()

        # Use wrong token
        verification_data = {"email": user.email, "token": "invalid-token-12345"}

        response = self.client.post(
            "/api/v1/users/verify-email/", verification_data, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid verification token" in response.data["error"]

        # Verify user is still not verified
        user.refresh_from_db()
        assert user.is_verified is False

    def test_verify_email_with_expired_token(self):
        """Test email verification fails with expired token."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = False
        token = user.generate_verification_token()

        # Set token creation time to 25 hours ago (expired after 24 hours)
        user.verification_token_created_at = timezone.now() - timedelta(hours=25)
        user.save()

        verification_data = {"email": user.email, "token": token}

        response = self.client.post(
            "/api/v1/users/verify-email/", verification_data, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in response.data["error"].lower()

        # Verify user is still not verified
        user.refresh_from_db()
        assert user.is_verified is False

    def test_verify_email_already_verified(self):
        """Test verifying an already verified email."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = True
        user.save()

        verification_data = {"email": user.email, "token": "any-token"}

        response = self.client.post(
            "/api/v1/users/verify-email/", verification_data, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "already verified" in response.data["message"].lower()

    def test_verify_email_missing_fields(self):
        """Test email verification fails without required fields."""
        # Missing token
        response = self.client.post(
            "/api/v1/users/verify-email/", {"email": "test@test.com"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Email and token are required" in response.data["error"]

        # Missing email
        response = self.client.post(
            "/api/v1/users/verify-email/", {"token": "some-token"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_email_user_not_found(self):
        """Test email verification with non-existent user."""
        verification_data = {
            "email": "nonexistent@test.com",
            "token": "some-token",
        }

        response = self.client.post(
            "/api/v1/users/verify-email/", verification_data, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "User not found" in response.data["error"]

    def test_resend_verification_email(self):
        """Test resending verification email."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = False
        user.save()

        # Mock the Celery task
        with patch(
            "apps.notifications.tasks.send_verification_email.delay"
        ) as mock_task:
            mock_task.side_effect = lambda user_id: self._send_verification_email_sync(
                user_id
            )

            response = self.client.post(
                "/api/v1/users/resend-verification/",
                {"email": user.email},
                format="json",
            )

            assert response.status_code == status.HTTP_200_OK
            assert "resent" in response.data["message"].lower()
            mock_task.assert_called_once_with(user.id)

    def test_resend_verification_already_verified(self):
        """Test resending verification to already verified user."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = True
        user.save()

        response = self.client.post(
            "/api/v1/users/resend-verification/",
            {"email": user.email},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert "already verified" in response.data["message"].lower()

    def test_resend_verification_nonexistent_user(self):
        """Test resending verification for non-existent user (security check)."""
        # Should not reveal whether user exists or not
        response = self.client.post(
            "/api/v1/users/resend-verification/",
            {"email": "nonexistent@test.com"},
            format="json",
        )

        # Returns 200 OK to not leak user existence
        assert response.status_code == status.HTTP_200_OK
        assert "If an account with this email exists" in response.data["message"]

    def test_verification_token_generation(self):
        """Test verification token generation and validation."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = False
        user.save()

        # Generate token
        token = user.generate_verification_token()

        assert token is not None
        assert len(token) > 20  # Should be a secure random token
        assert user.verification_token == token
        assert user.verification_token_created_at is not None

        # Token should be valid immediately
        assert user.is_verification_token_valid() is True

        # Token should become invalid after expiry
        user.verification_token_created_at = timezone.now() - timedelta(hours=25)
        user.save()
        assert user.is_verification_token_valid() is False

    def test_verify_email_method(self):
        """Test the verify_email model method."""
        user = self.create_patient(email="test@test.com")
        user.is_verified = False
        user.generate_verification_token()

        # Verify email using model method
        user.verify_email()

        assert user.is_verified is True
        assert user.verification_token is None
        assert user.verification_token_created_at is None

    # Helper method for synchronous email sending in tests
    def _send_verification_email_sync(self, user_id):
        """Synchronously send verification email for testing."""
        from apps.notifications.tasks import send_verification_email

        # Execute the task synchronously
        user = User.objects.get(id=user_id)
        token = user.generate_verification_token()

        # Instead of actually sending email, just verify the logic works
        # In real tests with email backend, you'd check mail.outbox
        return f"Email would be sent to {user.email} with token {token}"


class EmailVerificationIntegrationTests(BaseTestCase):
    """Integration tests for email verification with actual email backend."""

    def test_complete_registration_and_verification_flow(self):
        """Test complete user flow from registration to email verification."""
        # Step 1: Register new user
        registration_data = {
            "email": "integration@test.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
            "first_name": "Integration",
            "last_name": "Test",
            "lab_client_id": 1,
        }

        with patch(
            "apps.notifications.tasks.send_verification_email.delay"
        ) as mock_task:
            # Make task execute synchronously for testing
            def sync_send(user_id):
                user = User.objects.get(id=user_id)
                user.generate_verification_token()
                return f"Email sent to {user.email}"

            mock_task.side_effect = sync_send

            # Register
            response = self.client.post(
                "/api/v1/users/register/", registration_data, format="json"
            )

            assert response.status_code == status.HTTP_201_CREATED

            # Get user
            user = User.objects.get(email="integration@test.com")
            assert user.is_verified is False

            # Step 2: Verify email
            verification_data = {
                "email": user.email,
                "token": user.verification_token,
            }

            response = self.client.post(
                "/api/v1/users/verify-email/", verification_data, format="json"
            )

            assert response.status_code == status.HTTP_200_OK

            # Step 3: Verify user is now verified and can log in
            user.refresh_from_db()
            assert user.is_verified is True

            # User should now be able to authenticate
            # (In real implementation, you might block unverified users from logging in)

    def test_token_uniqueness(self):
        """Test that each token generated is unique."""
        user = self.create_patient(email="test@test.com")

        tokens = set()
        for _ in range(10):
            token = user.generate_verification_token()
            assert token not in tokens
            tokens.add(token)
