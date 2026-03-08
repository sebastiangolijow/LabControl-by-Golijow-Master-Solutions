# LabControl - Hostinger VPS Deployment Plan

**Created**: 2026-02-22
**Target Platform**: Hostinger VPS
**Deployment Strategy**: Docker Compose on VPS with automated backups

---

## Table of Contents

1. [Infrastructure Overview](#infrastructure-overview)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [VPS Setup & Hardening](#vps-setup--hardening)
4. [Docker & Application Deployment](#docker--application-deployment)
5. [Backup Strategy (CRITICAL)](#backup-strategy-critical)
6. [SSL/TLS Configuration](#ssltls-configuration)
7. [DNS Configuration](#dns-configuration)
8. [Monitoring & Maintenance](#monitoring--maintenance)
9. [Rollback & Disaster Recovery](#rollback--disaster-recovery)
10. [Alternative: Managed Container Service](#alternative-managed-container-service)

---

## Infrastructure Overview

### Architecture

```
Internet
    ↓
DNS (Hostinger) → lab.yourdomain.com
    ↓
Hostinger VPS (Ubuntu 22.04 LTS)
    ↓
┌─────────────────────────────────────────┐
│  Firewall (UFW) + Fail2Ban              │
├─────────────────────────────────────────┤
│  Nginx (Reverse Proxy + SSL)            │
├─────────────────────────────────────────┤
│  Docker Compose Stack:                  │
│    - Web (Django + Gunicorn)            │
│    - Celery Worker                      │
│    - Celery Beat                        │
│    - PostgreSQL 15                      │
│    - Redis 7                            │
│    - Frontend (Vue SPA - static files)  │
├─────────────────────────────────────────┤
│  Automated Backups:                     │
│    - PostgreSQL dumps (daily)           │
│    - Media files (daily)                │
│    - Offsite storage (Hostinger Object  │
│      Storage or S3-compatible)          │
└─────────────────────────────────────────┘
```

### Recommended VPS Specs

**Minimum**:
- **CPU**: 2 vCPU cores
- **RAM**: 4 GB
- **Storage**: 50 GB SSD
- **Bandwidth**: Unlimited (typical Hostinger offering)
- **OS**: Ubuntu 22.04 LTS

**Recommended** (for better performance):
- **CPU**: 4 vCPU cores
- **RAM**: 8 GB
- **Storage**: 80 GB SSD

---

## Pre-Deployment Checklist

### 1. Domain & DNS Preparation
- [ ] Purchase/configure domain through Hostinger
- [ ] Verify domain ownership
- [ ] Prepare DNS records (A record for VPS IP)

### 2. Hostinger VPS Setup
- [ ] Provision VPS with Ubuntu 22.04 LTS
- [ ] Note down root password and IP address
- [ ] Configure SSH key authentication
- [ ] Disable root SSH login (security)

### 3. Application Preparation
- [ ] Review and update production settings (`config/settings/prod.py`)
- [ ] Generate secure `DJANGO_SECRET_KEY`
- [ ] Configure email settings (SMTP)
- [ ] Prepare environment variables
- [ ] Build and test production Docker images locally

### 4. Backup Infrastructure
- [ ] Set up Hostinger Object Storage or external S3 bucket
- [ ] Configure backup credentials
- [ ] Test backup/restore procedures

---

## VPS Setup & Hardening

### Step 1: Initial Server Setup (15 minutes)

```bash
# SSH into VPS
ssh root@YOUR_VPS_IP

# Update system packages
apt update && apt upgrade -y

# Set timezone
timedatectl set-timezone America/Argentina/Buenos_Aires  # Adjust to your timezone

# Create non-root user
adduser deploy
usermod -aG sudo deploy

# Configure SSH key for deploy user
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### Step 2: SSH Hardening (10 minutes)

```bash
# Edit SSH config
nano /etc/ssh/sshd_config

# Make these changes:
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
Port 22  # Or change to custom port (e.g., 2222) for additional security

# Restart SSH
systemctl restart sshd

# IMPORTANT: Test SSH connection with deploy user before logging out!
# Open new terminal and test:
ssh deploy@YOUR_VPS_IP
```

### Step 3: Firewall Setup (10 minutes)

```bash
# Switch to deploy user
su - deploy

# Configure UFW firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH (or your custom port)
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable

# Verify firewall status
sudo ufw status verbose
```

### Step 4: Fail2Ban Installation (10 minutes)

```bash
# Install Fail2Ban
sudo apt install fail2ban -y

# Create custom configuration
sudo nano /etc/fail2ban/jail.local
```

Add this configuration:

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
destemail = your-email@example.com
sendername = Fail2Ban
action = %(action_mwl)s

[sshd]
enabled = true
port = 22
logpath = /var/log/auth.log

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log

[nginx-noscript]
enabled = true
port = http,https
logpath = /var/log/nginx/access.log

[nginx-badbots]
enabled = true
port = http,https
logpath = /var/log/nginx/access.log
```

```bash
# Start and enable Fail2Ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Check status
sudo fail2ban-client status
```

### Step 5: Install Docker & Docker Compose (15 minutes)

```bash
# Remove old Docker versions (if any)
sudo apt remove docker docker-engine docker.io containerd runc

# Install prerequisites
sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add deploy user to docker group
sudo usermod -aG docker deploy

# Log out and back in for group changes to take effect
exit
ssh deploy@YOUR_VPS_IP

# Verify Docker installation
docker --version
docker compose version

# Enable Docker to start on boot
sudo systemctl enable docker
```

### Step 6: Install Nginx (10 minutes)

```bash
# Install Nginx
sudo apt install nginx -y

# Enable Nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# Verify Nginx is running
sudo systemctl status nginx
```

---

## Docker & Application Deployment

### Step 1: Prepare Application Directory (5 minutes)

```bash
# Create application directory
sudo mkdir -p /opt/labcontrol
sudo chown deploy:deploy /opt/labcontrol
cd /opt/labcontrol

# Clone repository (or upload files via rsync/scp)
# Option A: Git clone (if repo is private, configure SSH key)
git clone https://github.com/yourusername/labcontrol.git .

# Option B: Upload via rsync from local machine
# (Run this from your LOCAL machine, not VPS)
# rsync -avz --exclude 'node_modules' --exclude '__pycache__' \
#   /Users/cevichesmac/Desktop/labcontrol/ deploy@YOUR_VPS_IP:/opt/labcontrol/
```

### Step 2: Create Production Environment File (10 minutes)

```bash
# Create .env.production file
nano /opt/labcontrol/.env.production
```

Add the following (replace with actual values):

```env
# Django
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=your-super-secret-key-here-generate-with-openssl-rand-base64-32
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=lab.yourdomain.com,www.lab.yourdomain.com,YOUR_VPS_IP

# Database
POSTGRES_DB=labcontrol_db
POSTGRES_USER=labcontrol_user
POSTGRES_PASSWORD=strong-database-password-here
DATABASE_URL=postgresql://labcontrol_user:strong-database-password-here@db:5432/labcontrol_db

# Redis & Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# Email (using Gmail SMTP as example)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-specific-password

# Frontend
FRONTEND_URL=https://lab.yourdomain.com

# Security
CSRF_TRUSTED_ORIGINS=https://lab.yourdomain.com,https://www.lab.yourdomain.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# Backup (configure after setting up object storage)
BACKUP_S3_BUCKET=labcontrol-backups
BACKUP_S3_ENDPOINT=https://storage.hostinger.com  # Or your S3-compatible endpoint
BACKUP_S3_ACCESS_KEY=your-access-key
BACKUP_S3_SECRET_KEY=your-secret-key
```

### Step 3: Create Production Docker Compose File (15 minutes)

```bash
nano /opt/labcontrol/docker-compose.prod.yml
```

```yaml
version: '3.9'

services:
  # PostgreSQL database with production settings
  db:
    image: postgres:15-alpine
    container_name: labcontrol_db
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups/postgres:/backups  # For manual backups
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - PGDATA=/var/lib/postgresql/data/pgdata
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - labcontrol_network
    # Don't expose port externally in production
    expose:
      - "5432"

  # Redis for caching and Celery broker
  redis:
    image: redis:7-alpine
    container_name: labcontrol_redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - labcontrol_network
    expose:
      - "6379"

  # Django web application with Gunicorn
  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: labcontrol_web
    restart: unless-stopped
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2 --timeout 60 --access-logfile - --error-logfile -
    volumes:
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    expose:
      - "8000"
    env_file:
      - .env.production
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - labcontrol_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Nginx reverse proxy
  nginx:
    image: nginx:alpine
    container_name: labcontrol_nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - static_volume:/app/staticfiles:ro
      - media_volume:/app/media:ro
      - ./frontend/dist:/usr/share/nginx/html:ro  # Vue.js production build
      - ./nginx/logs:/var/log/nginx
    depends_on:
      - web
    networks:
      - labcontrol_network

  # Celery worker for background tasks
  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: labcontrol_celery_worker
    restart: unless-stopped
    command: celery -A config worker -l info --concurrency=2
    volumes:
      - media_volume:/app/media
    env_file:
      - .env.production
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - labcontrol_network

  # Celery beat for scheduled tasks
  celery_beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: labcontrol_celery_beat
    restart: unless-stopped
    command: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    env_file:
      - .env.production
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - labcontrol_network

volumes:
  postgres_data:
    name: labcontrol_postgres_data
  redis_data:
    name: labcontrol_redis_data
  static_volume:
    name: labcontrol_static
  media_volume:
    name: labcontrol_media

networks:
  labcontrol_network:
    name: labcontrol_network
    driver: bridge
```

### Step 4: Configure Nginx (20 minutes)

```bash
# Create Nginx directory structure
mkdir -p /opt/labcontrol/nginx/{conf.d,ssl,logs}

# Create main Nginx configuration
nano /opt/labcontrol/nginx/nginx.conf
```

```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_size "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 20M;  # For file uploads

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    include /etc/nginx/conf.d/*.conf;
}
```

Create site configuration:

```bash
nano /opt/labcontrol/nginx/conf.d/labcontrol.conf
```

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name lab.yourdomain.com www.lab.yourdomain.com;

    # Allow Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server configuration
server {
    listen 443 ssl http2;
    server_name lab.yourdomain.com www.lab.yourdomain.com;

    # SSL certificates (will be configured with Let's Encrypt)
    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logs
    access_log /var/log/nginx/labcontrol_access.log;
    error_log /var/log/nginx/labcontrol_error.log;

    # Client body size (for file uploads)
    client_max_body_size 20M;

    # Serve static files (Vue.js frontend)
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # Django static files
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Django media files (user uploads)
    location /media/ {
        alias /app/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Proxy API requests to Django
    location /api/ {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Django admin
    location /admin/ {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check endpoint
    location /health/ {
        proxy_pass http://web:8000;
        access_log off;
    }
}
```

### Step 5: Build and Deploy (20 minutes)

```bash
# Navigate to application directory
cd /opt/labcontrol

# Build Vue.js frontend for production (from local machine, then upload)
# On LOCAL machine:
cd /Users/cevichesmac/Desktop/labcontrol-frontend
npm run build
# Upload dist folder to VPS:
rsync -avz dist/ deploy@YOUR_VPS_IP:/opt/labcontrol/frontend/dist/

# Back on VPS:
cd /opt/labcontrol

# Build Docker images
docker compose -f docker-compose.prod.yml build

# Start services (without SSL first, we'll add it next)
docker compose -f docker-compose.prod.yml up -d db redis

# Wait for DB to be ready (check with docker logs)
docker logs labcontrol_db

# Run database migrations
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate

# Create superuser
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser

# Collect static files
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput

# Create seed users (optional)
docker compose -f docker-compose.prod.yml run --rm web python manage.py create_seed_users

# Start all services
docker compose -f docker-compose.prod.yml up -d

# Check logs
docker compose -f docker-compose.prod.yml logs -f
```

---

## Backup Strategy (CRITICAL)

### Daily Automated Backups

Create backup script:

```bash
sudo mkdir -p /opt/labcontrol/scripts
sudo nano /opt/labcontrol/scripts/backup.sh
```

```bash
#!/bin/bash
# LabControl Backup Script
# Performs PostgreSQL dump and media files backup

set -e  # Exit on error

# Configuration
BACKUP_DIR="/opt/labcontrol/backups"
DATE=$(date +%Y%m%d_%H%M%S)
POSTGRES_CONTAINER="labcontrol_db"
POSTGRES_USER="labcontrol_user"
POSTGRES_DB="labcontrol_db"
RETENTION_DAYS=30  # Keep backups for 30 days

# S3-compatible storage (Hostinger Object Storage or AWS S3)
S3_BUCKET="${BACKUP_S3_BUCKET}"
S3_ENDPOINT="${BACKUP_S3_ENDPOINT}"
S3_ACCESS_KEY="${BACKUP_S3_ACCESS_KEY}"
S3_SECRET_KEY="${BACKUP_S3_SECRET_KEY}"

# Create backup directories
mkdir -p "${BACKUP_DIR}/postgres"
mkdir -p "${BACKUP_DIR}/media"
mkdir -p "${BACKUP_DIR}/logs"

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "${BACKUP_DIR}/logs/backup.log"
}

log "=== Starting LabControl Backup ==="

# 1. PostgreSQL Backup
log "Backing up PostgreSQL database..."
docker exec ${POSTGRES_CONTAINER} pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > "${BACKUP_DIR}/postgres/db_${DATE}.sql.gz"

if [ $? -eq 0 ]; then
    log "PostgreSQL backup successful: db_${DATE}.sql.gz"
else
    log "ERROR: PostgreSQL backup failed!"
    exit 1
fi

# 2. Media Files Backup
log "Backing up media files..."
docker run --rm \
    -v labcontrol_media:/media:ro \
    -v ${BACKUP_DIR}/media:/backup \
    alpine tar czf /backup/media_${DATE}.tar.gz -C /media .

if [ $? -eq 0 ]; then
    log "Media files backup successful: media_${DATE}.tar.gz"
else
    log "ERROR: Media files backup failed!"
    exit 1
fi

# 3. Upload to S3-compatible storage (if configured)
if [ -n "$S3_BUCKET" ] && [ -n "$S3_ACCESS_KEY" ]; then
    log "Uploading backups to object storage..."

    # Install s3cmd if not present
    if ! command -v s3cmd &> /dev/null; then
        log "Installing s3cmd..."
        sudo apt install -y s3cmd
    fi

    # Configure s3cmd (one-time setup)
    if [ ! -f ~/.s3cfg ]; then
        cat > ~/.s3cfg << EOF
[default]
access_key = ${S3_ACCESS_KEY}
secret_key = ${S3_SECRET_KEY}
host_base = ${S3_ENDPOINT}
host_bucket = ${S3_BUCKET}
use_https = True
EOF
    fi

    # Upload database backup
    s3cmd put "${BACKUP_DIR}/postgres/db_${DATE}.sql.gz" "s3://${S3_BUCKET}/postgres/"

    # Upload media backup
    s3cmd put "${BACKUP_DIR}/media/media_${DATE}.tar.gz" "s3://${S3_BUCKET}/media/"

    log "Backups uploaded to object storage"
else
    log "S3 storage not configured, skipping offsite backup"
fi

# 4. Clean old local backups (keep last 30 days)
log "Cleaning old local backups (older than ${RETENTION_DAYS} days)..."
find "${BACKUP_DIR}/postgres" -name "db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}/media" -name "media_*.tar.gz" -mtime +${RETENTION_DAYS} -delete

log "=== Backup Completed Successfully ==="

# Send notification (optional - requires configured email)
# echo "LabControl backup completed successfully on $(date)" | mail -s "Backup Success" your-email@example.com
```

Make script executable and test:

```bash
sudo chmod +x /opt/labcontrol/scripts/backup.sh

# Test backup manually (load env vars first)
source /opt/labcontrol/.env.production
sudo -E /opt/labcontrol/scripts/backup.sh
```

### Schedule Daily Backups with Cron

```bash
# Edit crontab
crontab -e

# Add this line to run backup daily at 2 AM
0 2 * * * /bin/bash -c 'source /opt/labcontrol/.env.production && /opt/labcontrol/scripts/backup.sh' >> /opt/labcontrol/backups/logs/cron.log 2>&1
```

### Restore Procedure

Create restore script:

```bash
sudo nano /opt/labcontrol/scripts/restore.sh
```

```bash
#!/bin/bash
# LabControl Restore Script

set -e

BACKUP_DIR="/opt/labcontrol/backups"
POSTGRES_CONTAINER="labcontrol_db"
POSTGRES_USER="labcontrol_user"
POSTGRES_DB="labcontrol_db"

# Check if backup file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo "Available backups:"
    ls -lh ${BACKUP_DIR}/postgres/
    exit 1
fi

BACKUP_FILE="$1"

echo "WARNING: This will restore from backup and OVERWRITE current data!"
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Stop web services
echo "Stopping web services..."
docker compose -f /opt/labcontrol/docker-compose.prod.yml stop web celery_worker celery_beat

# Restore database
echo "Restoring database from ${BACKUP_FILE}..."
gunzip < "${BACKUP_FILE}" | docker exec -i ${POSTGRES_CONTAINER} psql -U ${POSTGRES_USER} ${POSTGRES_DB}

# Restart services
echo "Restarting services..."
docker compose -f /opt/labcontrol/docker-compose.prod.yml up -d

echo "Restore completed successfully!"
```

```bash
sudo chmod +x /opt/labcontrol/scripts/restore.sh
```

---

## SSL/TLS Configuration

### Option 1: Let's Encrypt with Certbot (Recommended - Free)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Stop Nginx temporarily (or use standalone mode)
docker compose -f /opt/labcontrol/docker-compose.prod.yml stop nginx

# Generate SSL certificate
sudo certbot certonly --standalone \
    -d lab.yourdomain.com \
    -d www.lab.yourdomain.com \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email

# Copy certificates to Nginx SSL directory
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/fullchain.pem /opt/labcontrol/nginx/ssl/
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/privkey.pem /opt/labcontrol/nginx/ssl/
sudo chown deploy:deploy /opt/labcontrol/nginx/ssl/*.pem

# Restart Nginx
docker compose -f /opt/labcontrol/docker-compose.prod.yml up -d nginx

# Set up auto-renewal
sudo crontab -e
# Add this line:
0 0 * * * certbot renew --quiet --deploy-hook "cp /etc/letsencrypt/live/lab.yourdomain.com/*.pem /opt/labcontrol/nginx/ssl/ && docker restart labcontrol_nginx"
```

### Option 2: Hostinger SSL (If available through hosting panel)

Follow Hostinger's SSL installation guide and upload certificates to `/opt/labcontrol/nginx/ssl/`.

---

## DNS Configuration

### Hostinger DNS Settings

In Hostinger DNS management panel:

1. **A Record** for main domain:
   - **Type**: A
   - **Host**: @ (or leave blank)
   - **Points to**: YOUR_VPS_IP
   - **TTL**: 14400 (4 hours) or Auto

2. **A Record** for www subdomain:
   - **Type**: A
   - **Host**: www
   - **Points to**: YOUR_VPS_IP
   - **TTL**: 14400

3. **(Optional) CNAME for subdomain**:
   - **Type**: CNAME
   - **Host**: lab
   - **Points to**: yourdomain.com
   - **TTL**: 14400

**DNS Propagation**: Wait 15 minutes to 48 hours (usually < 1 hour)

Verify DNS:
```bash
# Check from local machine
dig lab.yourdomain.com
nslookup lab.yourdomain.com
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# Create health check script
nano /opt/labcontrol/scripts/health_check.sh
```

```bash
#!/bin/bash
# Health Check Script

DOMAIN="https://lab.yourdomain.com"
HEALTH_ENDPOINT="${DOMAIN}/health/"

# Check if site is responding
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" ${HEALTH_ENDPOINT})

if [ "$HTTP_CODE" -eq 200 ]; then
    echo "✓ Health check passed (HTTP ${HTTP_CODE})"
    exit 0
else
    echo "✗ Health check failed (HTTP ${HTTP_CODE})"
    # Send alert (configure email or webhook)
    echo "LabControl health check failed at $(date)" | mail -s "ALERT: LabControl Down" your-email@example.com
    exit 1
fi
```

```bash
chmod +x /opt/labcontrol/scripts/health_check.sh

# Add to crontab (check every 5 minutes)
crontab -e
*/5 * * * * /opt/labcontrol/scripts/health_check.sh >> /opt/labcontrol/logs/health.log 2>&1
```

### Useful Monitoring Commands

```bash
# View all container status
docker compose -f docker-compose.prod.yml ps

# View logs (all services)
docker compose -f docker-compose.prod.yml logs -f

# View logs (specific service)
docker compose -f docker-compose.prod.yml logs -f web

# Resource usage
docker stats

# Disk usage
df -h
docker system df

# Database size
docker exec labcontrol_db psql -U labcontrol_user -d labcontrol_db -c "SELECT pg_size_pretty(pg_database_size('labcontrol_db'));"
```

### Log Rotation

```bash
# Install logrotate if not present
sudo apt install logrotate -y

# Create logrotate config for Nginx
sudo nano /etc/logrotate.d/labcontrol
```

```
/opt/labcontrol/nginx/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 deploy deploy
    sharedscripts
    postrotate
        docker exec labcontrol_nginx nginx -s reload > /dev/null 2>&1 || true
    endscript
}
```

---

## Rollback & Disaster Recovery

### Quick Rollback Procedure

```bash
# 1. Stop all services
docker compose -f /opt/labcontrol/docker-compose.prod.yml down

# 2. Restore from latest backup
/opt/labcontrol/scripts/restore.sh /opt/labcontrol/backups/postgres/db_YYYYMMDD_HHMMSS.sql.gz

# 3. Restart services
docker compose -f /opt/labcontrol/docker-compose.prod.yml up -d
```

### Full Disaster Recovery

If VPS is completely lost:

1. **Provision new VPS** following [VPS Setup & Hardening](#vps-setup--hardening)
2. **Restore application code** from Git repository
3. **Restore environment variables** from secure storage (password manager)
4. **Download backups** from object storage
5. **Restore database and media files** using restore script
6. **Reconfigure DNS** to point to new VPS IP
7. **Generate new SSL certificates**

**Recovery Time Objective (RTO)**: ~2-4 hours
**Recovery Point Objective (RPO)**: 24 hours (daily backups)

---

## Alternative: Managed Container Service

### Option: Hostinger Managed WordPress → Docker

If Hostinger offers managed container services (check their documentation), consider:

**Pros:**
- Automated updates and patches
- Built-in monitoring
- Easier scaling
- Managed backups

**Cons:**
- Higher cost
- Less control
- Potential vendor lock-in

**Recommendation**: For a small lab application, the VPS approach with Docker Compose is more cost-effective and provides sufficient control. Managed services make sense when scaling to multiple instances or requiring high availability.

---

## Deployment Checklist

### Pre-Launch Checklist

- [ ] VPS provisioned and hardened (SSH, firewall, fail2ban)
- [ ] Docker and Docker Compose installed
- [ ] Application code deployed
- [ ] Environment variables configured
- [ ] Database migrations run
- [ ] Static files collected
- [ ] Superuser created
- [ ] DNS configured and propagated
- [ ] SSL certificates installed
- [ ] Nginx configured and tested
- [ ] All services running (`docker compose ps`)
- [ ] Backup script tested and scheduled
- [ ] Health checks configured
- [ ] Log rotation configured

### Post-Launch Checklist

- [ ] Test user registration and login
- [ ] Test file uploads (study results)
- [ ] Test email notifications
- [ ] Verify backups are running daily
- [ ] Monitor logs for errors (first 24 hours)
- [ ] Set up monitoring alerts
- [ ] Document admin credentials securely
- [ ] Share access with team members
- [ ] Plan maintenance windows

---

## Maintenance Schedule

### Daily (Automated)
- Automated backups at 2 AM
- Health checks every 5 minutes
- Log rotation (Nginx logs)

### Weekly (Manual - 15 minutes)
- Review application logs for errors
- Check disk space usage
- Verify backup integrity (test restore)
- Review Fail2Ban logs
- Update Ubuntu packages: `sudo apt update && sudo apt upgrade -y`

### Monthly (Manual - 30 minutes)
- Review and update Docker images
- Security audit (check for CVEs)
- Performance review (database size, query optimization)
- Review and optimize backup retention policy

### Quarterly (Manual - 1 hour)
- Full disaster recovery test
- Security penetration testing (basic)
- Capacity planning review

---

## Emergency Contacts & Documentation

**Critical Access Information** (store in password manager):
- VPS IP Address
- SSH Private Key location
- Database credentials
- Django SECRET_KEY
- Email SMTP credentials
- Object storage credentials
- Domain registrar login
- Hostinger panel login

**Documentation Links**:
- Django Production Checklist: https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/
- Docker Compose Production: https://docs.docker.com/compose/production/
- Nginx Security: https://nginx.org/en/docs/http/configuring_https_servers.html
- PostgreSQL Backup: https://www.postgresql.org/docs/15/backup.html

---

## Cost Estimate (Monthly)

**Hostinger VPS** (4 vCPU, 8GB RAM, 80GB SSD): ~$15-30/month
**Domain** (if new): ~$10-15/year
**Object Storage** (50GB): ~$2-5/month
**SSL Certificate**: Free (Let's Encrypt)

**Total**: ~$20-40/month

---

## Next Steps

1. **Provision VPS** on Hostinger
2. **Follow this deployment plan** step by step
3. **Test thoroughly** before going live
4. **Schedule** a maintenance window announcement
5. **Deploy** during low-traffic hours
6. **Monitor** closely for first 24-48 hours

---

*Last Updated: 2026-02-22*
*Version: 1.0*
*Maintained by: LabControl DevOps Team*
