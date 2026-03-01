#!/bin/bash
#
# LabControl Backup Script
# Performs PostgreSQL dump and media files backup
#
# Usage: ./backup.sh
# Schedule: Run daily via cron at 2 AM
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/labcontrol/backups}"
DATE=$(date +%Y%m%d_%H%M%S)
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-labcontrol_db}"
POSTGRES_USER="${POSTGRES_USER:-labcontrol_user}"
POSTGRES_DB="${POSTGRES_DB:-labcontrol_db}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"  # Keep backups for 30 days

# S3-compatible storage (Hostinger Object Storage or AWS S3)
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
S3_ACCESS_KEY="${BACKUP_S3_ACCESS_KEY:-}"
S3_SECRET_KEY="${BACKUP_S3_SECRET_KEY:-}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create backup directories
mkdir -p "${BACKUP_DIR}/postgres"
mkdir -p "${BACKUP_DIR}/media"
mkdir -p "${BACKUP_DIR}/logs"

# Log function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "${BACKUP_DIR}/logs/backup.log"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "${BACKUP_DIR}/logs/backup.log"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "${BACKUP_DIR}/logs/backup.log"
}

log "======================================"
log "Starting LabControl Backup"
log "======================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    error "Docker is not running!"
    exit 1
fi

# Check if database container is running
if ! docker ps | grep -q ${POSTGRES_CONTAINER}; then
    error "PostgreSQL container ${POSTGRES_CONTAINER} is not running!"
    exit 1
fi

# 1. PostgreSQL Backup
log "Backing up PostgreSQL database..."
if docker exec ${POSTGRES_CONTAINER} pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > "${BACKUP_DIR}/postgres/db_${DATE}.sql.gz"; then
    BACKUP_SIZE=$(du -h "${BACKUP_DIR}/postgres/db_${DATE}.sql.gz" | cut -f1)
    log "PostgreSQL backup successful: db_${DATE}.sql.gz (${BACKUP_SIZE})"
else
    error "PostgreSQL backup failed!"
    exit 1
fi

# 2. Media Files Backup
log "Backing up media files..."
if docker run --rm \
    -v labcontrol_media:/media:ro \
    -v ${BACKUP_DIR}/media:/backup \
    alpine tar czf /backup/media_${DATE}.tar.gz -C /media . 2>/dev/null; then
    MEDIA_SIZE=$(du -h "${BACKUP_DIR}/media/media_${DATE}.tar.gz" | cut -f1)
    log "Media files backup successful: media_${DATE}.tar.gz (${MEDIA_SIZE})"
else
    error "Media files backup failed!"
    exit 1
fi

# 3. Upload to S3-compatible storage (if configured)
if [ -n "$S3_BUCKET" ] && [ -n "$S3_ACCESS_KEY" ]; then
    log "Uploading backups to object storage..."

    # Install s3cmd if not present
    if ! command -v s3cmd &> /dev/null; then
        log "Installing s3cmd..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y s3cmd
        elif command -v yum &> /dev/null; then
            sudo yum install -y s3cmd
        else
            warning "Could not install s3cmd. Skipping offsite backup."
        fi
    fi

    if command -v s3cmd &> /dev/null; then
        # Configure s3cmd (one-time setup)
        S3CFG_FILE="${HOME}/.s3cfg"
        if [ ! -f "$S3CFG_FILE" ]; then
            log "Configuring s3cmd..."
            cat > "$S3CFG_FILE" << EOF
[default]
access_key = ${S3_ACCESS_KEY}
secret_key = ${S3_SECRET_KEY}
host_base = ${S3_ENDPOINT}
host_bucket = %(bucket)s.${S3_ENDPOINT}
use_https = True
signature_v2 = False
EOF
            chmod 600 "$S3CFG_FILE"
        fi

        # Upload database backup
        log "Uploading database backup..."
        if s3cmd put "${BACKUP_DIR}/postgres/db_${DATE}.sql.gz" "s3://${S3_BUCKET}/postgres/" --no-progress; then
            log "Database backup uploaded successfully"
        else
            warning "Failed to upload database backup to S3"
        fi

        # Upload media backup
        log "Uploading media backup..."
        if s3cmd put "${BACKUP_DIR}/media/media_${DATE}.tar.gz" "s3://${S3_BUCKET}/media/" --no-progress; then
            log "Media backup uploaded successfully"
        else
            warning "Failed to upload media backup to S3"
        fi
    fi
else
    warning "S3 storage not configured (BACKUP_S3_BUCKET or BACKUP_S3_ACCESS_KEY missing)"
    warning "Backups are stored locally only. Configure S3 for offsite backup!"
fi

# 4. Clean old local backups (keep last N days)
log "Cleaning old local backups (older than ${RETENTION_DAYS} days)..."
DELETED_COUNT=0

# Clean old database backups
DELETED=$(find "${BACKUP_DIR}/postgres" -name "db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
DELETED_COUNT=$((DELETED_COUNT + DELETED))

# Clean old media backups
DELETED=$(find "${BACKUP_DIR}/media" -name "media_*.tar.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
DELETED_COUNT=$((DELETED_COUNT + DELETED))

if [ "$DELETED_COUNT" -gt 0 ]; then
    log "Deleted ${DELETED_COUNT} old backup(s)"
else
    log "No old backups to delete"
fi

# 5. Backup summary
log "======================================"
log "Backup Summary"
log "======================================"
log "Database backup: ${BACKUP_DIR}/postgres/db_${DATE}.sql.gz (${BACKUP_SIZE})"
log "Media backup: ${BACKUP_DIR}/media/media_${DATE}.tar.gz (${MEDIA_SIZE})"

# Count total backups
DB_BACKUPS=$(find "${BACKUP_DIR}/postgres" -name "db_*.sql.gz" | wc -l)
MEDIA_BACKUPS=$(find "${BACKUP_DIR}/media" -name "media_*.tar.gz" | wc -l)
log "Total backups: ${DB_BACKUPS} database, ${MEDIA_BACKUPS} media"

# Disk usage
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
log "Total backup directory size: ${TOTAL_SIZE}"

log "======================================"
log "Backup Completed Successfully"
log "======================================"

# Optional: Send notification via email (requires mail command)
# Uncomment and configure if needed:
# if command -v mail &> /dev/null; then
#     echo "LabControl backup completed successfully on $(date)" | \
#         mail -s "LabControl Backup Success" your-email@example.com
# fi

exit 0
