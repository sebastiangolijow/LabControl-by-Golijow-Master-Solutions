#!/bin/bash
# Database Restore - Restore PostgreSQL database from backup

set -e

BACKUP_DIR="/opt/labcontrol/backups"

# Check if backup file is provided
if [ -z "$1" ]; then
    echo "❌ Error: No backup file specified"
    echo ""
    echo "Usage: ./restore-db.sh <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh $BACKUP_DIR/*.sql.gz 2>/dev/null | tail -10 || echo "No backups found in $BACKUP_DIR"
    exit 1
fi

BACKUP_FILE="$1"

# Check if file exists
if [ ! -f "$BACKUP_FILE" ]; then
    # Try looking in backup directory
    if [ -f "${BACKUP_DIR}/${BACKUP_FILE}" ]; then
        BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
    else
        echo "❌ Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
fi

echo "⚠️  WARNING: This will REPLACE the current database with the backup!"
echo "Backup file: $BACKUP_FILE"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Restore cancelled"
    exit 1
fi

echo ""
echo "🔄 Restoring database from backup..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd /opt/labcontrol

# Create a safety backup first
echo "💾 Creating safety backup of current database..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker-compose -f docker-compose.prod.yml exec -T db pg_dump -U labcontrol_user labcontrol_db | gzip > "${BACKUP_DIR}/pre_restore_backup_${TIMESTAMP}.sql.gz"
echo "✅ Safety backup created: pre_restore_backup_${TIMESTAMP}.sql.gz"
echo ""

# Decompress if needed
if [[ $BACKUP_FILE == *.gz ]]; then
    echo "🗜️  Decompressing backup..."
    TEMP_SQL="${BACKUP_FILE%.gz}"
    gunzip -c "$BACKUP_FILE" > "$TEMP_SQL"
    SQL_FILE="$TEMP_SQL"
else
    SQL_FILE="$BACKUP_FILE"
fi

# Drop existing connections
echo "🔌 Dropping existing database connections..."
docker-compose -f docker-compose.prod.yml exec -T db psql -U labcontrol_user -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'labcontrol_db' AND pid <> pg_backend_pid();"

# Restore database
echo "📥 Restoring database..."
cat "$SQL_FILE" | docker-compose -f docker-compose.prod.yml exec -T db psql -U labcontrol_user labcontrol_db

# Clean up temp file if we decompressed
if [[ $BACKUP_FILE == *.gz ]]; then
    rm -f "$TEMP_SQL"
fi

echo ""
echo "✅ Database restored successfully!"
echo ""
echo "🔄 Restarting Django application..."
docker-compose -f docker-compose.prod.yml restart web celery_worker celery_beat

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Restore complete"
