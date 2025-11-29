# Celery & Celery Beat Setup Guide

This document explains how to properly set up and use Celery and Celery Beat in LabControl.

## Overview

LabControl uses:
- **Celery** for asynchronous task execution
- **Celery Beat** for scheduled/periodic tasks
- **django-celery-beat** for database-backed scheduling
- **Redis** as message broker and result backend

## Architecture

```
┌──────────────┐       ┌──────────┐       ┌───────────────┐
│ Django App   │──────>│  Redis   │<──────│ Celery Worker │
└──────────────┘       └──────────┘       └───────────────┘
                             ▲
                             │
                       ┌─────┴──────┐
                       │ Celery Beat│
                       └────────────┘
```

## Services in Docker Compose

### 1. `web` - Django Application
Main application that enqueues tasks.

### 2. `celery_worker` - Task Executor
Executes async tasks from the queue.
```bash
docker-compose logs -f celery_worker
```

### 3. `celery_beat` - Scheduler
Triggers periodic tasks on schedule.
```bash
docker-compose logs -f celery_beat
```

### 4. `flower` - Monitoring Dashboard
Web UI for monitoring Celery tasks.
- URL: http://localhost:5555
- Shows tasks, workers, queues, etc.

## Setup Instructions

### 1. Ensure Migrations Are Run

The `django-celery-beat` app requires database tables:

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# You should see migrations for:
# - django_celery_beat
# - django_celery_results
```

### 2. Set Up Periodic Tasks

**Option A: Using Management Command (Recommended)**

Run the built-in command to create default periodic tasks:

```bash
docker-compose exec web python manage.py setup_periodic_tasks
```

This creates:
- **Send Appointment Reminders**: Daily at 9:00 AM
- **Cleanup Old Notifications**: Weekly on Sunday at 2:00 AM

**Option B: Using Django Admin**

1. Access Django Admin: http://localhost:8000/admin
2. Login with superuser credentials
3. Navigate to **Periodic Tasks** section
4. Click **Add Periodic Task**
5. Fill in:
   - **Name**: Descriptive name (e.g., "Send Daily Reminders")
   - **Task**: Task path (e.g., `apps.appointments.tasks.send_appointment_reminders`)
   - **Schedule**: Choose Crontab, Interval, Solar, or Clocked
   - **Enabled**: Check to activate

**Option C: Programmatically**

```python
from django_celery_beat.models import CrontabSchedule, PeriodicTask

# Create schedule
schedule, _ = CrontabSchedule.objects.get_or_create(
    minute='0',
    hour='9',
    day_of_week='*',
    day_of_month='*',
    month_of_year='*',
)

# Create periodic task
PeriodicTask.objects.get_or_create(
    name='My Task',
    task='apps.myapp.tasks.my_task',
    crontab=schedule,
    enabled=True,
)
```

### 3. Start All Services

```bash
docker-compose up -d
```

### 4. Verify Celery Beat is Running

```bash
# Check logs
docker-compose logs -f celery_beat

# You should see:
# - "celery beat v5.3.6 is starting"
# - "DatabaseScheduler: Schedule changed"
# - No error messages
```

## Available Tasks

### Appointments App
**File**: `apps/appointments/tasks.py`

- `send_appointment_reminders()`: Sends reminders for appointments in next 24 hours

**Default Schedule**: Daily at 9:00 AM

### Notifications App
**File**: `apps/notifications/tasks.py`

- `send_email_notification(user_id, subject, message)`: Send email to user
- `cleanup_old_notifications()`: Delete read notifications older than 90 days
- `send_bulk_notification(user_ids, title, message, type)`: Send to multiple users

**Default Schedule**: Cleanup runs weekly on Sunday at 2:00 AM

## Creating New Tasks

### 1. Define Task in `tasks.py`

```python
# apps/myapp/tasks.py
from celery import shared_task
from django.core.mail import send_mail

@shared_task
def my_background_task(user_id):
    """Description of what this task does."""
    # Your task logic here
    return f"Completed for user {user_id}"
```

### 2. Call Task from Code

```python
# Synchronous (blocking)
result = my_background_task(123)

# Asynchronous (recommended)
task = my_background_task.delay(123)

# With countdown (delay execution)
task = my_background_task.apply_async(args=[123], countdown=60)  # 60 seconds

# With ETA (specific time)
from datetime import datetime, timedelta
eta = datetime.utcnow() + timedelta(hours=1)
task = my_background_task.apply_async(args=[123], eta=eta)
```

### 3. Make Task Periodic (Optional)

Add via Django Admin or management command as shown above.

## Monitoring & Debugging

### Check Worker Status

```bash
# View worker logs
docker-compose logs -f celery_worker

# Check if worker is processing tasks
docker-compose exec celery_worker celery -A config inspect active
```

### Check Beat Status

```bash
# View beat logs
docker-compose logs -f celery_beat

# Check registered periodic tasks
docker-compose exec web python manage.py shell
>>> from django_celery_beat.models import PeriodicTask
>>> PeriodicTask.objects.filter(enabled=True).values('name', 'task')
```

### Using Flower Dashboard

1. Open http://localhost:5555
2. View:
   - **Workers**: Active workers and their status
   - **Tasks**: Running, queued, succeeded, failed tasks
   - **Broker**: Queue status
   - **Monitor**: Real-time task execution

### Task Results

Tasks results are stored in database (`django-celery-results`):

```python
from django_celery_results.models import TaskResult

# Get recent task results
recent = TaskResult.objects.order_by('-date_created')[:10]

# Check specific task
task_id = "abc123-def456..."
result = TaskResult.objects.get(task_id=task_id)
print(result.status)  # SUCCESS, FAILURE, PENDING, etc.
print(result.result)  # Task return value
```

## Common Issues & Solutions

### Issue 1: Celery Beat Not Starting

**Symptoms:**
- Container exits immediately
- Error: "Table doesn't exist"

**Solution:**
```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Restart beat
docker-compose restart celery_beat
```

### Issue 2: Tasks Not Executing

**Check:**
1. Is worker running? `docker-compose ps celery_worker`
2. Are tasks registered? Check worker logs on startup
3. Is task enabled? Check Django Admin -> Periodic Tasks

**Solution:**
```bash
# Restart worker
docker-compose restart celery_worker

# Check registered tasks
docker-compose exec celery_worker celery -A config inspect registered
```

### Issue 3: Beat Schedule Not Updating

**Solution:**
Beat checks database every 5 seconds by default. If changes don't appear:
```bash
# Restart beat
docker-compose restart celery_beat
```

### Issue 4: Tasks Failing Silently

**Enable Verbose Logging:**

In `config/settings/dev.py`:
```python
CELERY_WORKER_LOGLEVEL = 'DEBUG'
```

Then restart:
```bash
docker-compose restart celery_worker celery_beat
```

## Best Practices

### 1. Task Design
- ✅ Keep tasks **idempotent** (safe to retry)
- ✅ Keep tasks **short** (< 5 minutes)
- ✅ Use **meaningful names**
- ✅ Add **docstrings** explaining what task does
- ❌ Don't pass large objects (pass IDs instead)
- ❌ Don't use Django ORM objects directly

**Good:**
```python
@shared_task
def process_study_results(study_id):
    study = Study.objects.get(id=study_id)
    # Process...
```

**Bad:**
```python
@shared_task
def process_study_results(study_object):  # ❌ Can't serialize
    # Process...
```

### 2. Error Handling
```python
@shared_task(bind=True, max_retries=3)
def my_task(self, user_id):
    try:
        # Task logic
        pass
    except Exception as exc:
        # Retry after 60 seconds
        raise self.retry(exc=exc, countdown=60)
```

### 3. Monitoring
- Check Flower dashboard regularly
- Monitor task failure rates
- Set up alerts for stuck tasks
- Review worker logs for errors

### 4. Periodic Task Scheduling
- Use crontab for complex schedules (daily, weekly, etc.)
- Use interval for simple repeating tasks (every N minutes)
- Disable tasks during maintenance
- Test schedules in staging first

## Production Considerations

### 1. Worker Scaling
```bash
# Run multiple workers
docker-compose up -d --scale celery_worker=3
```

### 2. Task Routing
Route different tasks to different queues:

```python
# config/celery.py
app.conf.task_routes = {
    'apps.studies.tasks.process_large_file': {'queue': 'heavy'},
    'apps.notifications.tasks.*': {'queue': 'notifications'},
}
```

### 3. Rate Limiting
```python
@shared_task(rate_limit='10/m')  # 10 times per minute
def rate_limited_task():
    pass
```

### 4. Task Timeouts
```python
@shared_task(time_limit=300, soft_time_limit=270)  # 5 min hard, 4.5 min soft
def long_running_task():
    pass
```

## Testing Celery Tasks

### In Tests
```python
# tests/test_tasks.py
from apps.appointments.tasks import send_appointment_reminders

class TestCeleryTasks(TestCase):
    def test_send_reminders(self):
        # Task runs synchronously in tests (see config/settings/test.py)
        result = send_appointment_reminders()
        assert "Sent" in result
```

### Manual Testing
```bash
# Django shell
docker-compose exec web python manage.py shell

>>> from apps.appointments.tasks import send_appointment_reminders
>>> result = send_appointment_reminders.delay()
>>> result.id  # Task ID
>>> result.ready()  # Is it done?
>>> result.result  # Get result
```

## Quick Reference

```bash
# Start all services
docker-compose up -d

# View specific service logs
docker-compose logs -f celery_worker
docker-compose logs -f celery_beat

# Restart services
docker-compose restart celery_worker celery_beat

# Run migrations
docker-compose exec web python manage.py migrate

# Setup periodic tasks
docker-compose exec web python manage.py setup_periodic_tasks

# Django shell
docker-compose exec web python manage.py shell

# Access Flower
open http://localhost:5555

# Check worker status
docker-compose exec celery_worker celery -A config inspect active

# Purge all tasks (careful!)
docker-compose exec celery_worker celery -A config purge
```

## Additional Resources

- [Celery Documentation](https://docs.celeryq.dev/)
- [django-celery-beat Documentation](https://django-celery-beat.readthedocs.io/)
- [Flower Documentation](https://flower.readthedocs.io/)

---

**Need Help?**
If you encounter issues not covered here, check:
1. Docker logs: `docker-compose logs`
2. Flower dashboard: http://localhost:5555
3. Django Admin: Periodic Tasks section
