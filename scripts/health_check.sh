#!/bin/bash
#
# LabControl Health Check Script
# Monitors application health and sends alerts if down
#
# Usage: ./health_check.sh
# Schedule: Run every 5 minutes via cron
#

set -u

DOMAIN="${DOMAIN:-https://lab.yourdomain.com}"
HEALTH_ENDPOINT="${DOMAIN}/health/"
ALERT_EMAIL="${ALERT_EMAIL:-}"
LOG_FILE="${LOG_FILE:-/opt/labcontrol/logs/health.log}"

# Timeout for curl (seconds)
TIMEOUT=10

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Check if site is responding
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time ${TIMEOUT} "${HEALTH_ENDPOINT}" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓${NC} Health check passed (HTTP ${HTTP_CODE})"
    log "✓ Health check passed (HTTP ${HTTP_CODE})"
    exit 0
else
    echo -e "${RED}✗${NC} Health check failed (HTTP ${HTTP_CODE})"
    log "✗ Health check failed (HTTP ${HTTP_CODE})"

    # Check if Docker containers are running
    log "Checking Docker containers..."
    CONTAINERS_STATUS=$(docker ps --filter "name=labcontrol_" --format "{{.Names}}: {{.Status}}" 2>/dev/null || echo "Could not check Docker containers")
    log "$CONTAINERS_STATUS"

    # Send alert email (if configured)
    if [ -n "$ALERT_EMAIL" ] && command -v mail &> /dev/null; then
        {
            echo "LabControl health check FAILED at $(date)"
            echo ""
            echo "Health endpoint: ${HEALTH_ENDPOINT}"
            echo "HTTP Status: ${HTTP_CODE}"
            echo ""
            echo "Docker containers status:"
            echo "$CONTAINERS_STATUS"
        } | mail -s "ALERT: LabControl Health Check Failed" "$ALERT_EMAIL"
        log "Alert email sent to ${ALERT_EMAIL}"
    fi

    exit 1
fi
