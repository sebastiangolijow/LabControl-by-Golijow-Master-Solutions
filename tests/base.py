"""
Base test class for LabControl platform.

Provides common test utilities, fixtures, and helpers following TDD best practices.
Inspired by production backends with extensive test infrastructure.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import User


class BaseTestMixin:
    """
    Mixin with common test utilities and factories.

    This mixin provides all the common functionality without inheriting
    from any test base class, allowing it to be used with both TestCase
    and TransactionTestCase.
    """

    def setUp(self):
        """Set up for each test method."""
        super().setUp()
        self.client = APIClient()
        self._user_counter = 0

    def tearDown(self):
        """Clean up after each test."""
        super().tearDown()

    # ======================
    # User Factories
    # ======================

    def create_user(self, role="patient", **kwargs):
        """
        Factory for creating users with any role.

        Args:
            role: User role (admin, lab_manager, technician, doctor, patient, staff)
            **kwargs: Additional user fields to override

        Returns:
            User instance
        """
        self._user_counter += 1
        defaults = {
            "email": kwargs.get("email", f"test{self._user_counter}@labcontrol.test"),
            "first_name": "Test",
            "last_name": "User",
            "role": role,
            "is_active": True,
        }
        defaults.update(kwargs)

        # Extract password separately as it needs special handling
        password = defaults.pop("password", "testpass123")

        user = User.objects.create_user(password=password, **defaults)
        return user

    def create_admin(self, **kwargs):
        """Create an admin user."""
        kwargs.setdefault("role", "admin")
        kwargs.setdefault("is_staff", True)
        kwargs.setdefault("is_superuser", True)
        return self.create_user(**kwargs)

    def create_lab_manager(self, lab_client_id=1, **kwargs):
        """Create a lab manager user."""
        kwargs.setdefault("role", "lab_manager")
        kwargs.setdefault("lab_client_id", lab_client_id)
        kwargs.setdefault("is_staff", True)
        return self.create_user(**kwargs)

    def create_lab_staff(self, lab_client_id=1, **kwargs):
        """Create a lab staff user."""
        kwargs.setdefault("role", "lab_staff")
        kwargs.setdefault("lab_client_id", lab_client_id)
        return self.create_user(**kwargs)

    def create_technician(self, lab_client_id=1, **kwargs):
        """Create a laboratory technician user."""
        kwargs.setdefault("role", "technician")
        kwargs.setdefault("lab_client_id", lab_client_id)
        return self.create_user(**kwargs)

    def create_doctor(self, **kwargs):
        """Create a doctor user."""
        kwargs.setdefault("role", "doctor")
        return self.create_user(**kwargs)

    def create_patient(self, **kwargs):
        """Create a patient user."""
        kwargs.setdefault("role", "patient")
        return self.create_user(**kwargs)

    # ======================
    # Study Factories
    # ======================

    def create_study_type(self, **kwargs):
        """
        Factory for creating study types.

        Returns:
            StudyType instance
        """
        from apps.studies.models import StudyType

        # Increment counter to ensure unique codes
        self._user_counter += 1

        defaults = {
            "name": "Complete Blood Count",
            "code": f"CBC{self._user_counter}",
            "description": "Complete blood count test",
            "category": "Hematology",
            "base_price": Decimal("50.00"),
            "requires_fasting": False,
            "estimated_processing_hours": 24,
            "is_active": True,
        }
        defaults.update(kwargs)
        return StudyType.objects.create(**defaults)

    def create_study(self, patient=None, study_type=None, **kwargs):
        """
        Factory for creating studies.

        Args:
            patient: Patient user (created if not provided)
            study_type: StudyType (created if not provided)

        Returns:
            Study instance
        """
        from apps.studies.models import Study

        if patient is None:
            patient = self.create_patient()
        if study_type is None:
            study_type = self.create_study_type()

        defaults = {
            "patient": patient,
            "study_type": study_type,
            "order_number": f"ORD-2024-{self._user_counter:04d}",
            "status": "pending",
            "lab_client_id": patient.lab_client_id or 1,
        }
        defaults.update(kwargs)
        return Study.objects.create(**defaults)

    # ======================
    # Appointment Factories
    # ======================

    def create_appointment(self, patient=None, study=None, **kwargs):
        """
        Factory for creating appointments.

        Args:
            patient: Patient user (created if not provided)
            study: Related study (optional)

        Returns:
            Appointment instance
        """
        from apps.appointments.models import Appointment

        if patient is None:
            patient = self.create_patient()

        # Increment counter to ensure unique appointment numbers
        self._user_counter += 1

        # Default to tomorrow at 10 AM
        tomorrow = timezone.now().date() + timedelta(days=1)

        defaults = {
            "patient": patient,
            "study": study,
            "appointment_number": f"APT-2024-{self._user_counter:04d}",
            "scheduled_date": tomorrow,
            "scheduled_time": time(10, 0),
            "duration_minutes": 30,
            "status": "scheduled",
            "lab_client_id": patient.lab_client_id or 1,
        }
        defaults.update(kwargs)
        return Appointment.objects.create(**defaults)

    # ======================
    # Payment Factories
    # ======================

    def create_invoice(self, patient=None, study=None, **kwargs):
        """
        Factory for creating invoices.

        Args:
            patient: Patient user (created if not provided)
            study: Related study (optional)

        Returns:
            Invoice instance
        """
        from apps.payments.models import Invoice

        if patient is None:
            patient = self.create_patient()

        # Increment counter to ensure unique invoice numbers
        self._user_counter += 1

        today = timezone.now().date()

        defaults = {
            "patient": patient,
            "study": study,
            "invoice_number": f"INV-2024-{self._user_counter:04d}",
            "status": "pending",
            "subtotal": Decimal("100.00"),
            "tax_amount": Decimal("10.00"),
            "discount_amount": Decimal("0.00"),
            "total_amount": Decimal("110.00"),
            "paid_amount": Decimal("0.00"),
            "issue_date": today,
            "due_date": today + timedelta(days=30),
            "lab_client_id": patient.lab_client_id or 1,
        }
        defaults.update(kwargs)
        return Invoice.objects.create(**defaults)

    def create_payment(self, invoice=None, **kwargs):
        """
        Factory for creating payments.

        Args:
            invoice: Invoice instance (created if not provided)

        Returns:
            Payment instance
        """
        from apps.payments.models import Payment

        if invoice is None:
            invoice = self.create_invoice()

        # Increment counter to ensure unique transaction IDs
        self._user_counter += 1

        defaults = {
            "invoice": invoice,
            "transaction_id": f"TXN-2024-{self._user_counter:04d}",
            "amount": invoice.total_amount,
            "payment_method": "credit_card",
            "status": "completed",
        }
        defaults.update(kwargs)
        return Payment.objects.create(**defaults)

    # ======================
    # Notification Factories
    # ======================

    def create_notification(self, user=None, **kwargs):
        """
        Factory for creating notifications.

        Args:
            user: User to notify (created if not provided)

        Returns:
            Notification instance
        """
        from apps.notifications.models import Notification

        if user is None:
            user = self.create_patient()

        defaults = {
            "user": user,
            "title": "Test Notification",
            "message": "This is a test notification",
            "notification_type": "info",
            "channel": "in_app",
            "status": "sent",
        }
        defaults.update(kwargs)
        return Notification.objects.create(**defaults)

    # ======================
    # Authentication Helpers
    # ======================

    def authenticate(self, user):
        """
        Authenticate API client as the given user.

        Args:
            user: User instance to authenticate as

        Returns:
            APIClient instance (self.client)
        """
        self.client.force_authenticate(user=user)
        return self.client

    def authenticate_as_patient(self):
        """Authenticate as a patient user."""
        user = self.create_patient()
        return self.authenticate(user), user

    def authenticate_as_lab_manager(self, lab_client_id=1, **kwargs):
        """Authenticate as a lab manager user."""
        user = self.create_lab_manager(lab_client_id=lab_client_id, **kwargs)
        return self.authenticate(user), user

    def authenticate_as_admin(self):
        """Authenticate as an admin user."""
        user = self.create_admin()
        return self.authenticate(user), user

    # ======================
    # Assertion Helpers
    # ======================

    def assertHasAttr(self, obj, attr, msg=None):
        """Assert that an object has a specific attribute."""
        if not hasattr(obj, attr):
            msg = msg or f"{obj} does not have attribute '{attr}'"
            raise AssertionError(msg)

    def assertUUID(self, value, msg=None):
        """Assert that a value is a valid UUID."""
        import uuid

        if not isinstance(value, uuid.UUID):
            msg = msg or f"{value} is not a UUID instance"
            raise AssertionError(msg)

    def assertTimestampRecent(self, timestamp, seconds=60, msg=None):
        """Assert that a timestamp is recent (within last N seconds)."""
        now = timezone.now()
        if abs((now - timestamp).total_seconds()) > seconds:
            msg = msg or f"Timestamp {timestamp} is not recent (now: {now})"
            raise AssertionError(msg)


class BaseTestCase(BaseTestMixin, TestCase):
    """
    Base test class with common utilities and factories.

    All test classes should inherit from this to get:
    - User factories for all roles
    - API client setup
    - Common assertions
    - Database cleanup
    """

    @classmethod
    def setUpTestData(cls):
        """Set up test data that's shared across all test methods."""
        super().setUpTestData()


class BaseTransactionTestCase(BaseTestMixin, TransactionTestCase):
    """
    Base transaction test case for tests that need database transactions.

    Use this for tests that involve:
    - Multiple database transactions
    - Database rollback testing
    - Celery task testing with database changes
    """

    pass
