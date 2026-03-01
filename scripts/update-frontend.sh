#!/bin/bash
# Update Frontend - Deploy new frontend build

set -e

echo "🔄 Updating LabControl Frontend..."

# Check if frontend build directory exists locally
if [ ! -d "/tmp/labcontrol-frontend-dist" ]; then
    echo "❌ Error: Frontend build not found at /tmp/labcontrol-frontend-dist"
    echo "Please build the frontend locally first:"
    echo "  cd ~/Desktop/labcontrol-frontend"
    echo "  npm run build"
    echo "  cp -r dist /tmp/labcontrol-frontend-dist"
    exit 1
fi

# Backup current frontend
echo "💾 Backing up current frontend..."
sudo cp -r /opt/labcontrol/frontend/dist /opt/labcontrol/frontend/dist.backup.$(date +%Y%m%d_%H%M%S)

# Deploy new frontend
echo "📤 Deploying new frontend build..."
sudo rm -rf /opt/labcontrol/frontend/dist
sudo cp -r /tmp/labcontrol-frontend-dist /opt/labcontrol/frontend/dist
sudo chown -R deploy:deploy /opt/labcontrol/frontend/dist

# Restart nginx to clear any cache
echo "🔄 Restarting Nginx..."
docker-compose -f /opt/labcontrol/docker-compose.prod.yml restart nginx

echo "✅ Frontend updated successfully!"
echo ""
echo "🌐 Access the application at:"
echo "   https://lab.srv879400.hstgr.cloud:8443"
