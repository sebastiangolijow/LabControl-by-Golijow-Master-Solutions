"""
Celery configuration for LabControl platform.

This module configures Celery for handling asynchronous tasks such as:
- Email notifications
- Report generation
- Data exports
- Scheduled appointment reminders
- LabWin sync and FTP PDF fetch
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

# Periodic tasks are managed via django-celery-beat DatabaseScheduler.
# Use the setup_periodic_tasks management command to create them:
#   python manage.py setup_periodic_tasks
#
# Scheduled tasks:
#   - sync_labwin_results: daily at 2:00 AM
#   - fetch_ftp_pdfs: every 30 minutes
#   - cleanup_ftp_pdfs: weekly Sunday 3:00 AM


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f"Request: {self.request!r}")
