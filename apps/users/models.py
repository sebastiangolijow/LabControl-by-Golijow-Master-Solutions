"""User models for the LabControl platform."""

import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model with email-based authentication.

    This model supports multi-tenant architecture where users can be associated
    with specific laboratory clients.

    Production features:
    - UUID for secure identification
    - Audit trail with django-simple-history
    - Multi-tenant support
    - Email-based authentication
    """

    # UUID for secure, non-enumerable identification
    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # Email is the primary identifier
    email = models.EmailField(_("email address"), unique=True)

    # Profile information
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    phone_number = models.CharField(_("phone number"), max_length=20, blank=True)

    # User role and permissions
    ROLE_CHOICES = [
        ("admin", _("Administrator")),
        ("lab_manager", _("Laboratory Manager")),
        ("technician", _("Laboratory Technician")),
        ("doctor", _("Doctor")),
        ("patient", _("Patient")),
        ("staff", _("Staff Member")),
    ]
    role = models.CharField(
        _("user role"),
        max_length=20,
        choices=ROLE_CHOICES,
        default="patient",
    )

    # Multi-tenant support - user can belong to a specific lab client
    # This will be a ForeignKey to a Lab/Client model (to be created later)
    lab_client_id = models.IntegerField(
        _("laboratory client ID"),
        null=True,
        blank=True,
        help_text=_("ID of the laboratory client this user belongs to"),
    )

    # Status flags
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into the admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    is_verified = models.BooleanField(
        _("verified"),
        default=False,
        help_text=_("Designates whether the user has verified their email address."),
    )

    # Timestamps
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    last_login = models.DateTimeField(_("last login"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    # Audit: Who created this user account (e.g., admin who created the account)
    created_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_users",
        verbose_name=_("created by"),
        help_text=_("User who created this account"),
    )

    # Use email for authentication
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # Email is required by default

    objects = UserManager()

    # Audit trail - track all changes to user records
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["uuid"]),
            models.Index(fields=["email"]),
            models.Index(fields=["lab_client_id"]),
            models.Index(fields=["role"]),
            models.Index(fields=["is_active", "role"]),  # Common query pattern
        ]

    def __str__(self):
        """String representation of the user."""
        return self.email

    def get_full_name(self):
        """Return the user's full name."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_short_name(self):
        """Return the user's short name (first name)."""
        return self.first_name or self.email

    @property
    def is_lab_manager(self):
        """Check if user is a laboratory manager."""
        return self.role == "lab_manager"

    @property
    def is_technician(self):
        """Check if user is a laboratory technician."""
        return self.role == "technician"

    @property
    def is_doctor(self):
        """Check if user is a doctor."""
        return self.role == "doctor"

    @property
    def is_patient(self):
        """Check if user is a patient."""
        return self.role == "patient"
