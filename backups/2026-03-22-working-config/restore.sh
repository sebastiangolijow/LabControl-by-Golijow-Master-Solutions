#!/bin/bash
# LabControl Configuration Restore Script
# Usage: ./restore.sh [nginx|env|full]

set -e

BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASSWORD="39872327Seba."
SERVER="deploy@72.60.137.226"
REMOTE_DIR="/opt/labcontrol"

echo "🔄 LabControl Configuration Restore"
echo "Backup: 2026-03-22 Working Configuration"
echo "Git Commit: e78c0e0"
echo ""

# Parse command
RESTORE_TYPE="${1:-nginx}"

case "$RESTORE_TYPE" in
  nginx)
    echo "📝 Restoring Nginx configuration only..."
    echo ""

    # Copy nginx config
    echo "→ Copying labcontrol.conf to server..."
    sshpass -p "$PASSWORD" scp "$BACKUP_DIR/labcontrol.conf" \
      "$SERVER:$REMOTE_DIR/nginx/conf.d/labcontrol.conf"

    # Restart nginx
    echo "→ Restarting nginx..."
    sshpass -p "$PASSWORD" ssh "$SERVER" \
      "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml restart nginx"

    echo ""
    echo "✅ Nginx configuration restored!"
    echo "→ Verifying..."
    sleep 2
    curl -I https://labmolecuar-portal-clientes-staging.com:8443/ 2>&1 | head -5
    ;;

  env)
    echo "📝 Restoring environment variables..."
    echo "⚠️  WARNING: This will recreate containers!"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Cancelled."
      exit 1
    fi

    # Copy .env.production
    echo "→ Copying .env.production to server..."
    sshpass -p "$PASSWORD" scp "$BACKUP_DIR/.env.production.backup" \
      "$SERVER:$REMOTE_DIR/.env.production"

    # Recreate containers
    echo "→ Recreating containers (this will take a moment)..."
    sshpass -p "$PASSWORD" ssh "$SERVER" \
      "cd $REMOTE_DIR && \
       docker compose -f docker-compose.prod.yml stop web celery_worker && \
       docker compose -f docker-compose.prod.yml rm -f web celery_worker && \
       docker compose -f docker-compose.prod.yml up -d"

    echo ""
    echo "✅ Environment variables restored!"
    ;;

  full)
    echo "📝 FULL RESTORE - This will restore ALL configuration"
    echo "⚠️  WARNING: This will:"
    echo "   - Restore nginx configuration"
    echo "   - Restore docker-compose.yml"
    echo "   - Restore environment variables"
    echo "   - Recreate all containers"
    echo ""
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Cancelled."
      exit 1
    fi

    # Copy all files
    echo "→ Copying all configuration files to server..."
    sshpass -p "$PASSWORD" scp "$BACKUP_DIR/labcontrol.conf" \
      "$SERVER:$REMOTE_DIR/nginx/conf.d/"
    sshpass -p "$PASSWORD" scp "$BACKUP_DIR/docker-compose.prod.yml" \
      "$SERVER:$REMOTE_DIR/"
    sshpass -p "$PASSWORD" scp "$BACKUP_DIR/.env.production.backup" \
      "$SERVER:$REMOTE_DIR/.env.production"

    # Rebuild and restart
    echo "→ Rebuilding and restarting all services..."
    sshpass -p "$PASSWORD" ssh "$SERVER" \
      "cd $REMOTE_DIR && \
       docker compose -f docker-compose.prod.yml down && \
       docker compose -f docker-compose.prod.yml up -d --build"

    echo ""
    echo "✅ Full restore complete!"
    echo "→ Waiting for services to start..."
    sleep 10
    echo "→ Verifying..."
    curl -I https://labmolecuar-portal-clientes-staging.com:8443/ 2>&1 | head -5
    ;;

  *)
    echo "Usage: $0 [nginx|env|full]"
    echo ""
    echo "Options:"
    echo "  nginx  - Restore only nginx configuration (quick, no downtime)"
    echo "  env    - Restore environment variables (requires container recreation)"
    echo "  full   - Full restore of all configuration (nuclear option)"
    exit 1
    ;;
esac

echo ""
echo "✅ Restore completed successfully!"
echo ""
echo "Verify with:"
echo "  Frontend: https://labmolecuar-portal-clientes-staging.com:8443"
echo "  Admin:    https://labmolecuar-portal-clientes-staging.com:8443/django-admin/"
