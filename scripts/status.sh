#!/bin/bash
# System Status - Check health of all services

set -e

echo "🏥 LabControl System Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd /opt/labcontrol

# Docker containers status
echo "📦 Docker Containers:"
docker-compose -f docker-compose.prod.yml ps
echo ""

# Disk usage
echo "💾 Disk Usage:"
df -h /opt/labcontrol
echo ""

# Database status
echo "🗄️  Database:"
docker-compose -f docker-compose.prod.yml exec -T db psql -U labcontrol_user -d labcontrol_db -c "SELECT version();" 2>/dev/null && echo "✅ PostgreSQL is running" || echo "❌ PostgreSQL is not accessible"
echo ""

# Redis status
echo "🔴 Redis:"
docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping 2>/dev/null && echo "✅ Redis is running" || echo "❌ Redis is not accessible"
echo ""

# Django health check
echo "🐍 Django Application:"
HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}" https://lab.srv879400.hstgr.cloud:8443/api/v1/health/ -k 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Django API is responding (HTTP $HTTP_CODE)"
else
    echo "❌ Django API is not responding (HTTP $HTTP_CODE)"
fi
echo ""

# Celery worker status
echo "⚙️  Celery Workers:"
CELERY_STATUS=$(docker-compose -f docker-compose.prod.yml exec -T celery_worker celery -A config inspect ping 2>/dev/null || echo "error")
if [[ $CELERY_STATUS == *"pong"* ]]; then
    echo "✅ Celery worker is running"
else
    echo "❌ Celery worker is not responding"
fi
echo ""

# Nginx status
echo "🌐 Nginx:"
NGINX_STATUS=$(curl -o /dev/null -s -w "%{http_code}" https://lab.srv879400.hstgr.cloud:8443 -k 2>/dev/null || echo "000")
if [ "$NGINX_STATUS" = "200" ]; then
    echo "✅ Nginx is serving the frontend (HTTP $NGINX_STATUS)"
else
    echo "❌ Nginx is not responding (HTTP $NGINX_STATUS)"
fi
echo ""

# Recent errors in Django logs
echo "⚠️  Recent Errors (last 10):"
docker-compose -f docker-compose.prod.yml logs --tail=1000 web 2>/dev/null | grep -i "error\|exception\|critical" | tail -10 || echo "No recent errors found"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Status check complete"
