"""
Celery configuration for LabControl platform.

This module configures Celery for handling asynchronous tasks such as:
- Email notifications
- Report generation
- Data exports
- Scheduled appointment reminders
"""
import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("labcontrol")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Note: When using django-celery-beat DatabaseScheduler, periodic tasks
# are managed through the Django admin interface, not here.
# To add periodic tasks:
# 1. Run: docker-compose exec web python manage.py migrate
# 2. Go to Django Admin -> Periodic Tasks
# 3. Add tasks like:
#    - apps.appointments.tasks.send_appointment_reminders (daily at 9 AM)
#    - apps.notifications.tasks.cleanup_old_notifications (weekly Sunday 2 AM)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f"Request: {self.request!r}")
