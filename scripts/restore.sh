#!/bin/bash
#
# LabControl Restore Script
# Restores PostgreSQL database from backup
#
# Usage: ./restore.sh <backup_file.sql.gz>
#

set -e
set -u

BACKUP_DIR="${BACKUP_DIR:-/opt/labcontrol/backups}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-labcontrol_db}"
POSTGRES_USER="${POSTGRES_USER:-labcontrol_user}"
POSTGRES_DB="${POSTGRES_DB:-labcontrol_db}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/labcontrol/docker-compose.prod.yml}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Check if backup file is provided
if [ $# -eq 0 ]; then
    error "No backup file specified!"
    echo ""
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Available database backups:"
    echo "======================================"
    ls -lh ${BACKUP_DIR}/postgres/ | grep "db_.*\.sql\.gz" || echo "No backups found"
    echo ""
    echo "Example:"
    echo "  $0 ${BACKUP_DIR}/postgres/db_20260222_020000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Validate backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    error "Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

# Display backup file info
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
BACKUP_DATE=$(stat -c %y "$BACKUP_FILE" 2>/dev/null || stat -f "%Sm" "$BACKUP_FILE")

echo "======================================"
echo "LabControl Database Restore"
echo "======================================"
echo "Backup file: ${BACKUP_FILE}"
echo "Backup size: ${BACKUP_SIZE}"
echo "Backup date: ${BACKUP_DATE}"
echo "======================================"
echo ""

# Final confirmation
warning "WARNING: This will OVERWRITE the current database!"
warning "All existing data will be LOST!"
echo ""
read -p "Are you absolutely sure you want to continue? Type 'yes' to proceed: " confirm

if [ "$confirm" != "yes" ]; then
    log "Restore cancelled by user"
    exit 0
fi

echo ""
log "Starting database restore..."

# Create a backup of the current database before restoring
CURRENT_BACKUP="${BACKUP_DIR}/postgres/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
log "Creating safety backup of current database: ${CURRENT_BACKUP}"

if docker exec ${POSTGRES_CONTAINER} pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > "${CURRENT_BACKUP}"; then
    log "Safety backup created successfully"
else
    error "Failed to create safety backup!"
    read -p "Continue anyway? (yes/no): " continue_anyway
    if [ "$continue_anyway" != "yes" ]; then
        exit 1
    fi
fi

# Stop web services to prevent database access during restore
log "Stopping web services..."
if [ -f "$COMPOSE_FILE" ]; then
    docker compose -f ${COMPOSE_FILE} stop web celery_worker celery_beat 2>/dev/null || true
else
    warning "Docker Compose file not found: ${COMPOSE_FILE}"
    warning "Attempting to stop containers directly..."
    docker stop labcontrol_web labcontrol_celery_worker labcontrol_celery_beat 2>/dev/null || true
fi

# Wait a moment for connections to close
sleep 3

# Drop all connections to the database
log "Terminating database connections..."
docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
    2>/dev/null || warning "Could not terminate all connections"

# Drop and recreate database
log "Recreating database..."
docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} -d postgres -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" || {
    error "Failed to drop database!"
    exit 1
}

docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} -d postgres -c "CREATE DATABASE ${POSTGRES_DB};" || {
    error "Failed to create database!"
    exit 1
}

# Restore database from backup
log "Restoring database from backup..."
if gunzip < "${BACKUP_FILE}" | docker exec -i ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} ${POSTGRES_DB} > /dev/null 2>&1; then
    log "Database restored successfully!"
else
    error "Database restore failed!"
    error "Attempting to restore from safety backup..."

    if [ -f "${CURRENT_BACKUP}" ]; then
        gunzip < "${CURRENT_BACKUP}" | docker exec -i ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} ${POSTGRES_DB}
        warning "Rolled back to safety backup"
    fi
    exit 1
fi

# Restart services
log "Restarting services..."
if [ -f "$COMPOSE_FILE" ]; then
    docker compose -f ${COMPOSE_FILE} up -d
else
    docker start labcontrol_web labcontrol_celery_worker labcontrol_celery_beat 2>/dev/null || true
fi

# Wait for services to start
log "Waiting for services to start..."
sleep 5

# Verify database is accessible
log "Verifying database..."
if docker exec ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} ${POSTGRES_DB} -c "SELECT COUNT(*) FROM django_migrations;" > /dev/null 2>&1; then
    log "Database verification successful!"
else
    warning "Database verification failed. Check logs: docker logs ${POSTGRES_CONTAINER}"
fi

echo ""
echo "======================================"
log "Restore Completed Successfully!"
echo "======================================"
log "Restored from: ${BACKUP_FILE}"
log "Safety backup saved at: ${CURRENT_BACKUP}"
log "Services restarted and running"
echo ""
log "Please verify the application is working correctly:"
log "  - Check web interface"
log "  - Test user login"
log "  - Verify data integrity"
echo ""

exit 0
