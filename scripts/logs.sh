#!/bin/bash
# View Application Logs - Easy log viewing with options

set -e

cd /opt/labcontrol

# Default service is web
SERVICE=${1:-web}
LINES=${2:-100}

echo "📋 Viewing logs for service: $SERVICE (last $LINES lines)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

case $SERVICE in
    web)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f web
        ;;
    celery|worker)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f celery_worker
        ;;
    beat)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f celery_beat
        ;;
    nginx)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f nginx
        ;;
    db|postgres)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f db
        ;;
    redis)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f redis
        ;;
    all)
        docker-compose -f docker-compose.prod.yml logs --tail=$LINES -f
        ;;
    *)
        echo "❌ Unknown service: $SERVICE"
        echo ""
        echo "Usage: ./logs.sh [SERVICE] [LINES]"
        echo ""
        echo "Available services:"
        echo "  web     - Django application logs (default)"
        echo "  celery  - Celery worker logs"
        echo "  beat    - Celery beat scheduler logs"
        echo "  nginx   - Nginx access/error logs"
        echo "  db      - PostgreSQL logs"
        echo "  redis   - Redis logs"
        echo "  all     - All services"
        echo ""
        echo "Examples:"
        echo "  ./logs.sh web 200      # Last 200 lines from Django"
        echo "  ./logs.sh celery       # Last 100 lines from Celery worker"
        echo "  ./logs.sh all 50       # Last 50 lines from all services"
        exit 1
        ;;
esac
