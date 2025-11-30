"""Signals for users app."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for post-save User events.

    This can be used to:
    - Send welcome emails
    - Create related profile objects
    - Log user creation
    - Trigger notifications
    """
    if created:
        # User was just created
        # TODO: Send welcome email
        # TODO: Create user profile
        # TODO: Log user registration
        pass
