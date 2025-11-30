"""Custom user manager for email-based authentication."""
from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserQuerySet(models.QuerySet):
    """
    Custom queryset for User model with chainable domain-specific methods.
    """

    def active(self):
        """Return only active users."""
        return self.filter(is_active=True)

    def inactive(self):
        """Return only inactive users."""
        return self.filter(is_active=False)

    def verified(self):
        """Return only users with verified email addresses."""
        return self.filter(is_verified=True)

    def unverified(self):
        """Return only users with unverified email addresses."""
        return self.filter(is_verified=False)

    def by_role(self, role):
        """Filter users by role."""
        return self.filter(role=role)

    def admins(self):
        """Return all admin users."""
        return self.filter(role="admin")

    def lab_managers(self):
        """Return all lab manager users."""
        return self.filter(role="lab_manager")

    def technicians(self):
        """Return all technician users."""
        return self.filter(role="technician")

    def doctors(self):
        """Return all doctor users."""
        return self.filter(role="doctor")

    def patients(self):
        """Return all patient users."""
        return self.filter(role="patient")

    def for_lab(self, lab_client_id):
        """Return users belonging to a specific lab."""
        return self.filter(lab_client_id=lab_client_id)

    def staff_members(self):
        """Return users who can access admin site."""
        return self.filter(is_staff=True)


class UserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    for authentication instead of username.

    Provides convenient methods for common user queries.
    """

    def get_queryset(self):
        """Return custom queryset."""
        return UserQuerySet(self.model, using=self._db)

    def active(self):
        """Get all active users."""
        return self.get_queryset().active()

    def inactive(self):
        """Get all inactive users."""
        return self.get_queryset().inactive()

    def verified(self):
        """Get all verified users."""
        return self.get_queryset().verified()

    def by_role(self, role):
        """Get users by role."""
        return self.get_queryset().by_role(role)

    def admins(self):
        """Get all admin users."""
        return self.get_queryset().admins()

    def lab_managers(self):
        """Get all lab manager users."""
        return self.get_queryset().lab_managers()

    def patients(self):
        """Get all patient users."""
        return self.get_queryset().patients()

    def for_lab(self, lab_client_id):
        """Get users for a specific lab."""
        return self.get_queryset().for_lab(lab_client_id)

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular User with the given email and password.
        """
        if not email:
            raise ValueError(_("The Email field must be set"))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)
