#!/bin/bash
# Database Backup - Create compressed backup of PostgreSQL database

set -e

BACKUP_DIR="/opt/labcontrol/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="labcontrol_backup_${TIMESTAMP}.sql"
COMPRESSED_FILE="${BACKUP_FILE}.gz"

echo "💾 Creating database backup..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

cd /opt/labcontrol

# Create backup
echo "📥 Dumping database..."
docker-compose -f docker-compose.prod.yml exec -T db pg_dump -U labcontrol_user labcontrol_db > "${BACKUP_DIR}/${BACKUP_FILE}"

# Compress backup
echo "🗜️  Compressing backup..."
gzip "${BACKUP_DIR}/${BACKUP_FILE}"

# Get file size
BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${COMPRESSED_FILE}" | cut -f1)

echo "✅ Backup created successfully!"
echo ""
echo "📁 Backup file: ${BACKUP_DIR}/${COMPRESSED_FILE}"
echo "📊 Size: ${BACKUP_SIZE}"
echo ""

# Clean up old backups (keep last 30 days)
echo "🧹 Cleaning up old backups (keeping last 30 days)..."
find $BACKUP_DIR -name "labcontrol_backup_*.sql.gz" -mtime +30 -delete

# List recent backups
echo ""
echo "📋 Recent backups:"
ls -lh $BACKUP_DIR | tail -10
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Backup complete"
