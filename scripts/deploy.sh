#!/bin/bash
#
# LabControl Deployment Script
# Quick deployment helper for production environment
#
# Usage: ./deploy.sh [command]
# Commands:
#   start    - Start all services
#   stop     - Stop all services
#   restart  - Restart all services
#   logs     - View logs (follow mode)
#   status   - Show container status
#   build    - Rebuild images
#   migrate  - Run database migrations
#   collect  - Collect static files
#   shell    - Open Django shell
#   dbshell  - Open PostgreSQL shell
#

set -e
set -u

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"
}

# Check if compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    error "Compose file not found: ${COMPOSE_FILE}"
    exit 1
fi

# Check if env file exists
if [ ! -f "$ENV_FILE" ]; then
    warning "Environment file not found: ${ENV_FILE}"
    warning "Please create ${ENV_FILE} from ${ENV_FILE}.template"
fi

# Command function
DC="docker compose -f ${COMPOSE_FILE}"

case "${1:-help}" in
    start)
        log "Starting LabControl services..."
        $DC up -d
        log "Services started. Use './deploy.sh logs' to view logs"
        log "Use './deploy.sh status' to check container status"
        ;;

    stop)
        log "Stopping LabControl services..."
        $DC down
        log "Services stopped"
        ;;

    restart)
        log "Restarting LabControl services..."
        $DC restart
        log "Services restarted"
        ;;

    logs)
        log "Showing logs (Ctrl+C to exit)..."
        $DC logs -f
        ;;

    status)
        log "Container status:"
        $DC ps
        echo ""
        log "Resource usage:"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
        ;;

    build)
        log "Building Docker images..."
        $DC build --no-cache
        log "Build complete"
        ;;

    rebuild)
        log "Rebuilding and restarting services..."
        $DC down
        $DC build --no-cache
        $DC up -d
        log "Rebuild complete"
        ;;

    migrate)
        log "Running database migrations..."
        $DC run --rm web python manage.py migrate
        log "Migrations complete"
        ;;

    collect)
        log "Collecting static files..."
        $DC run --rm web python manage.py collectstatic --noinput
        log "Static files collected"
        ;;

    shell)
        log "Opening Django shell..."
        $DC exec web python manage.py shell
        ;;

    dbshell)
        log "Opening PostgreSQL shell..."
        $DC exec db psql -U ${POSTGRES_USER:-labcontrol_user} ${POSTGRES_DB:-labcontrol_db}
        ;;

    createsuperuser)
        log "Creating superuser..."
        $DC exec web python manage.py createsuperuser
        ;;

    backup)
        log "Running backup script..."
        /opt/labcontrol/scripts/backup.sh
        ;;

    update)
        log "Updating application..."
        log "Pulling latest code..."
        git pull origin main

        log "Building new images..."
        $DC build

        log "Stopping services..."
        $DC down

        log "Running migrations..."
        $DC run --rm web python manage.py migrate

        log "Collecting static files..."
        $DC run --rm web python manage.py collectstatic --noinput

        log "Starting services..."
        $DC up -d

        log "Update complete!"
        ;;

    health)
        log "Checking service health..."

        # Check if containers are running
        RUNNING=$($DC ps --services --filter "status=running" | wc -l)
        TOTAL=$($DC ps --services | wc -l)

        echo "Running containers: ${RUNNING}/${TOTAL}"

        # Check web health endpoint
        if docker exec labcontrol_web curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
            log "✓ Web service is healthy"
        else
            error "✗ Web service is not responding"
        fi

        # Check database
        if docker exec labcontrol_db pg_isready -U ${POSTGRES_USER:-labcontrol_user} > /dev/null 2>&1; then
            log "✓ Database is healthy"
        else
            error "✗ Database is not responding"
        fi

        # Check Redis
        if docker exec labcontrol_redis redis-cli ping > /dev/null 2>&1; then
            log "✓ Redis is healthy"
        else
            error "✗ Redis is not responding"
        fi
        ;;

    help|*)
        echo "LabControl Deployment Helper"
        echo ""
        echo "Usage: ./deploy.sh [command]"
        echo ""
        echo "Commands:"
        echo "  start          - Start all services"
        echo "  stop           - Stop all services"
        echo "  restart        - Restart all services"
        echo "  logs           - View logs (follow mode)"
        echo "  status         - Show container status"
        echo "  build          - Rebuild Docker images"
        echo "  rebuild        - Rebuild and restart services"
        echo "  migrate        - Run database migrations"
        echo "  collect        - Collect static files"
        echo "  shell          - Open Django shell"
        echo "  dbshell        - Open PostgreSQL shell"
        echo "  createsuperuser - Create Django superuser"
        echo "  backup         - Run backup script"
        echo "  update         - Pull code, rebuild, migrate, restart"
        echo "  health         - Check service health"
        echo "  help           - Show this help message"
        echo ""
        ;;
esac
