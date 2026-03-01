#!/bin/bash
# Update Backend - Rebuild and restart backend services

set -e

echo "🔄 Updating LabControl Backend..."

cd /opt/labcontrol

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
git pull origin main

# Rebuild and restart services
echo "🔨 Rebuilding Docker containers..."
docker-compose -f docker-compose.prod.yml build web celery_worker celery_beat

echo "🔄 Restarting services..."
docker-compose -f docker-compose.prod.yml up -d --no-deps web celery_worker celery_beat

# Run migrations
echo "🗄️  Running database migrations..."
docker-compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput

# Collect static files
echo "📦 Collecting static files..."
docker-compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput

echo "✅ Backend updated successfully!"
echo ""
echo "📊 Service status:"
docker-compose -f docker-compose.prod.yml ps
