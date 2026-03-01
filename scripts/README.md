# LabControl Deployment Scripts

This directory contains utility scripts for managing the LabControl production deployment.

## Available Scripts

### 1. update-backend.sh
Updates the backend application code and restarts services.

```bash
./scripts/update-backend.sh
```

**What it does:**
- Pulls latest code from GitHub
- Rebuilds Docker containers (web, celery_worker, celery_beat)
- Restarts services with zero downtime
- Runs database migrations
- Collects static files
- Shows service status

**When to use:**
- After pushing backend code changes
- After updating dependencies
- After modifying Django settings

---

### 2. update-frontend.sh
Deploys a new frontend build to the server.

```bash
# First, build locally:
cd ~/Desktop/labcontrol-frontend
npm run build
cp -r dist /tmp/labcontrol-frontend-dist

# Then run on server:
./scripts/update-frontend.sh
```

**What it does:**
- Backs up current frontend
- Deploys new build from `/tmp/labcontrol-frontend-dist`
- Sets correct permissions
- Restarts Nginx

**When to use:**
- After making frontend changes
- After updating Vue.js dependencies
- After changing environment variables in frontend

---

### 3. backup-db.sh
Creates a compressed backup of the PostgreSQL database.

```bash
./scripts/backup-db.sh
```

**What it does:**
- Dumps PostgreSQL database to SQL file
- Compresses with gzip
- Saves to `/opt/labcontrol/backups/`
- Cleans up backups older than 30 days
- Shows backup size and location

**When to use:**
- Before major updates
- Before running migrations
- As part of regular backup routine
- Before restoring from backup

**Backups are stored at:** `/opt/labcontrol/backups/labcontrol_backup_YYYYMMDD_HHMMSS.sql.gz`

---

### 4. restore-db.sh
Restores the database from a backup file.

```bash
./scripts/restore-db.sh labcontrol_backup_20260301_123456.sql.gz
```

**What it does:**
- Creates a safety backup first
- Prompts for confirmation
- Drops existing database connections
- Restores from specified backup
- Restarts Django services

**When to use:**
- After accidental data loss
- When reverting to previous state
- When migrating data

⚠️ **WARNING:** This replaces the entire database!

---

### 5. logs.sh
View application logs easily.

```bash
./scripts/logs.sh [SERVICE] [LINES]
```

**Examples:**
```bash
./scripts/logs.sh web          # Last 100 lines from Django
./scripts/logs.sh web 200      # Last 200 lines from Django
./scripts/logs.sh celery       # Celery worker logs
./scripts/logs.sh nginx        # Nginx access/error logs
./scripts/logs.sh all 50       # Last 50 lines from all services
```

**Available services:**
- `web` - Django application (default)
- `celery` - Celery worker
- `beat` - Celery beat scheduler
- `nginx` - Nginx reverse proxy
- `db` - PostgreSQL database
- `redis` - Redis cache/broker
- `all` - All services

---

### 6. status.sh
Check health status of all services.

```bash
./scripts/status.sh
```

**What it shows:**
- Docker container status
- Disk usage
- PostgreSQL connectivity
- Redis connectivity
- Django API health (HTTP check)
- Celery worker status
- Nginx status
- Recent errors from logs

**When to use:**
- After deployment to verify everything works
- When troubleshooting issues
- As part of monitoring routine

---

## Automation

### Setup Automated Backups

Add to crontab to run daily backups at 2 AM:

```bash
crontab -e
```

Add this line:
```
0 2 * * * /opt/labcontrol/scripts/backup-db.sh >> /opt/labcontrol/logs/backup.log 2>&1
```

### Setup Daily Status Checks

Run status check every day at 8 AM:
```
0 8 * * * /opt/labcontrol/scripts/status.sh >> /opt/labcontrol/logs/status.log 2>&1
```

---

## Quick Reference

```bash
# Update backend after code changes
./scripts/update-backend.sh

# Deploy new frontend
./scripts/update-frontend.sh

# Backup database
./scripts/backup-db.sh

# Check system health
./scripts/status.sh

# View Django logs
./scripts/logs.sh web

# View Celery logs
./scripts/logs.sh celery

# Restore from backup
./scripts/restore-db.sh backups/labcontrol_backup_20260301_120000.sql.gz
```

---

## Troubleshooting

### Scripts don't run
Make sure they're executable:
```bash
chmod +x /opt/labcontrol/scripts/*.sh
```

### Permission denied
Some scripts may need sudo access. Make sure the `deploy` user has necessary permissions.

### Backup directory doesn't exist
Create it manually:
```bash
mkdir -p /opt/labcontrol/backups
```

---

## Notes

- All scripts assume they're run from the server at `/opt/labcontrol/`
- Scripts use `docker-compose.prod.yml` for production environment
- Backups are kept for 30 days by default
- Always test in staging environment first when possible
