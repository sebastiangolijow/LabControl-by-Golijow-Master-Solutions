# LabControl - Production Deployment Guide

**Last Updated:** March 1, 2026
**Server:** Hostinger VPS (srv879400.hstgr.cloud)
**Environment:** Production
**Status:** ✅ Fully Deployed and Operational

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Server Configuration](#server-configuration)
3. [Deployment Process](#deployment-process)
4. [Problems Solved](#problems-solved)
5. [Current Configuration](#current-configuration)
6. [Deployment Scripts](#deployment-scripts)
7. [Next Steps](#next-steps)
8. [Known Issues](#known-issues)
9. [Troubleshooting](#troubleshooting)

---

## Technology Stack

### Backend
- **Django 4.2** - Python web framework
- **Django REST Framework** - API framework
- **PostgreSQL 15** - Database with UUID primary keys
- **Redis 4.6.0** - Cache and Celery broker
- **Celery** - Async task queue
- **Gunicorn** - WSGI HTTP Server
- **django-redis** - Redis cache backend

### Frontend
- **Vue.js 3** - Progressive JavaScript framework
- **Vite 7.3.0** - Build tool
- **Pinia** - State management
- **Vue Router** - Client-side routing
- **Axios** - HTTP client

### Infrastructure
- **Docker + Docker Compose** - Containerization
- **Nginx** - Reverse proxy and static file server
- **Self-signed SSL** - HTTPS encryption
- **Ubuntu 24.04 LTS** - Operating system

---

## Server Configuration

### Server Details
```
Host: srv879400.hstgr.cloud
IP: 72.60.137.226
SSH User: deploy
SSH Password: 39872327Seba.
```

### Ports
- **8080** - HTTP (redirects to HTTPS)
- **8443** - HTTPS (main application)
- **5432** - PostgreSQL (internal)
- **6379** - Redis (internal)
- **5555** - Flower (Celery monitoring, internal)

### Directory Structure
```
/opt/labcontrol/
├── apps/                          # Django apps
├── config/                        # Django settings
│   └── settings/
│       ├── base.py
│       ├── dev.py
│       ├── prod.py               # Production settings
│       └── test.py
├── frontend/
│   └── dist/                     # Built Vue.js app
├── nginx/
│   ├── conf.d/
│   │   └── labcontrol.conf       # Nginx configuration
│   └── ssl/
│       ├── cert.pem              # Self-signed SSL certificate
│       └── key.pem               # SSL private key
├── docker-compose.prod.yml       # Production compose file
├── .env.production               # Environment variables
└── requirements/                 # Python dependencies
```

---

## Deployment Process

### Initial Setup (One-time)

#### 1. Server Preparation
```bash
# SSH into server
ssh deploy@72.60.137.226

# Install Docker and Docker Compose
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker deploy
```

#### 2. Upload Code
```bash
# From local machine
rsync -avz --exclude='node_modules' --exclude='venv' --exclude='__pycache__' \
  /Users/cevichesmac/Desktop/labcontrol/ deploy@72.60.137.226:/opt/labcontrol/
```

#### 3. Environment Configuration
Create `.env.production` on server:
```bash
# Database
DATABASE_URL=postgresql://labcontrol_user:labcontrol_pass@db:5432/labcontrol_db

# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_ALLOWED_HOSTS=lab.srv879400.hstgr.cloud,srv879400.hstgr.cloud,72.60.137.226
DEBUG=False

# CSRF & CORS
CSRF_TRUSTED_ORIGINS=https://lab.srv879400.hstgr.cloud:8443,https://srv879400.hstgr.cloud:8443
CORS_ALLOWED_ORIGINS=https://lab.srv879400.hstgr.cloud:8443,https://srv879400.hstgr.cloud:8443

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# Frontend
FRONTEND_URL=https://lab.srv879400.hstgr.cloud:8443

# Email (not configured yet)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

#### 4. Generate SSL Certificates
```bash
# On server
cd /opt/labcontrol/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/C=AR/ST=BuenosAires/L=BuenosAires/O=LDM/CN=lab.srv879400.hstgr.cloud"
```

#### 5. Build and Start Services
```bash
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

#### 6. Run Migrations
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

#### 7. Create Demo Data
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py create_demo_data
```

### Frontend Build and Deploy

#### Local Build
```bash
# On local machine
cd /Users/cevichesmac/Desktop/labcontrol-frontend

# Ensure .env.production has correct API URL
cat > .env.production << EOF
VITE_API_BASE_URL=https://lab.srv879400.hstgr.cloud:8443/api/v1
VITE_API_TIMEOUT=10000
VITE_APP_NAME=LabControl
VITE_APP_VERSION=1.0.0
VITE_FEATURE_CATALOG=false
EOF

# Build
npm run build

# Upload to server
scp -r dist/* deploy@72.60.137.226:/opt/labcontrol/frontend/dist/
```

---

## Problems Solved

### 1. Redis Version Incompatibility

**Problem:**
```
TypeError: AbstractConnection.__init__() got an unexpected keyword argument 'CLIENT_CLASS'
```

**Cause:** Redis 5.0.3 changed API, incompatible with Django's cache backend.

**Solution:**
1. Downgraded Redis from 5.0.3 to 4.6.0 in `requirements/base.txt`
2. Changed cache backend from `django.core.cache.backends.redis.RedisCache` to `django_redis.cache.RedisCache`
3. Updated `config/settings/prod.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",  # Changed from Django's built-in
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            }
        },
        "KEY_PREFIX": "labcontrol",
    }
}
```

### 2. CSRF Token Issues (Mobile Login)

**Problem:** Login worked in browser but failed on mobile with "CSRF token missing" error.

**Cause:**
- `CSRF_COOKIE_HTTPONLY = True` prevented JavaScript from reading the cookie
- `CSRF_COOKIE_SAMESITE = "Strict"` was too restrictive
- Frontend wasn't fetching CSRF cookie before login

**Solution:**

1. **Backend** (`config/settings/prod.py`):
```python
# Cookie settings
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Must be False so JavaScript can read it
SESSION_COOKIE_SAMESITE = "Lax"  # Changed from Strict to Lax
CSRF_COOKIE_SAMESITE = "Lax"  # Changed from Strict to Lax
```

2. **Frontend** (`src/api/client.js`):
```javascript
// Added CSRF token reading function
function getCsrfToken() {
  const name = 'csrftoken';
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Added withCredentials to axios
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  withCredentials: true,  // Enable credentials
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add CSRF token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // Add CSRF token for non-GET requests
  if (config.method !== 'get') {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken;
    }
  }

  return config;
});
```

3. **Frontend** (`src/api/auth.js`):
```javascript
async login(credentials) {
  // First, make a GET request to fetch the CSRF cookie
  await apiClient.get('/auth/user/').catch(() => {
    // Ignore 401 errors - we just need the CSRF cookie
  });

  const response = await apiClient.post('/auth/login/', credentials);
  return response.data;
}
```

4. **Backend CORS** (`config/settings/prod.py` and `dev.py`):
```python
CORS_ALLOW_CREDENTIALS = True
```

### 3. Database Password Authentication

**Problem:** PostgreSQL refused password authentication.

**Solution:** Hardcoded password in `docker-compose.prod.yml`:
```yaml
db:
  environment:
    POSTGRES_PASSWORD: labcontrol_pass
```

### 4. SSH Fail2ban IP Ban

**Problem:** Multiple failed SSH attempts banned local IP.

**Solution:**
```bash
# On server
fail2ban-client set sshd unbanip 92.177.110.63
```

### 5. Logout Not Redirecting

**Problem:** After logout, user stayed on the same page with no data.

**Solution:** Added redirect in `src/stores/auth.js`:
```javascript
import router from '@/router';

async logout() {
  try {
    if (this.refreshToken) {
      await authApi.logout(this.refreshToken);
    }
  } catch (error) {
    console.error('Logout API error:', error);
  } finally {
    this.user = null;
    this.accessToken = null;
    this.refreshToken = null;
    this.isAuthenticated = false;

    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');

    // Redirect to login page
    router.push('/login');
  }
}
```

---

## Current Configuration

### Active Users (Demo Data)

All passwords: `test1234`

**Admins:**
- carlos@labcontrol.com (Carlos Golijow)
- franco@labcontrol.com (Franco Siri)
- lucia@labcontrol.com (Lucia LDM)

**Patients:**
- patient+0@labcontrol.com (María González)
- patient+1@labcontrol.com (Juan Pérez)
- patient+2@labcontrol.com (Ana Martínez)
- m.simini@labcontrol.com (Mariana Simini)

**Doctors:**
- doctor+0@labcontrol.com (Dr. Roberto Fernández)
- doctor+1@labcontrol.com (Dr. Laura Rodríguez)

### Hidden Features
- **Catalog Tab:** Hidden via `VITE_FEATURE_CATALOG=false`
- **Appointments Tab:** Hidden via code comments in navigation components

### Mobile Optimizations
- Bottom navigation bar with key features
- Logout button in Profile page (hidden on desktop)
- Responsive layouts for all views

---

## Deployment Scripts

### Update Backend Script

Create `/opt/labcontrol/scripts/update-backend.sh`:

```bash
#!/bin/bash
# Update Backend Deployment Script

set -e

echo "🔄 Updating LabControl Backend..."

cd /opt/labcontrol

# Pull latest code (if using git)
# git pull origin main

echo "📦 Rebuilding Docker images..."
docker compose -f docker-compose.prod.yml build web

echo "🔄 Restarting services..."
docker compose -f docker-compose.prod.yml up -d web

echo "🗃️  Running migrations..."
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

echo "📊 Collecting static files..."
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

echo "✅ Backend updated successfully!"
```

### Update Frontend Script

Create `/opt/labcontrol/scripts/update-frontend.sh`:

```bash
#!/bin/bash
# Update Frontend Deployment Script

set -e

echo "🔄 Updating LabControl Frontend..."

# Check if dist directory exists locally
if [ ! -d "/tmp/frontend-dist" ]; then
  echo "❌ Error: Frontend build not found at /tmp/frontend-dist"
  echo "Please run this from your local machine with:"
  echo "  scp -r dist/* deploy@72.60.137.226:/tmp/frontend-dist/"
  exit 1
fi

# Backup current frontend
echo "💾 Backing up current frontend..."
cp -r /opt/labcontrol/frontend/dist /opt/labcontrol/frontend/dist.backup.$(date +%Y%m%d_%H%M%S)

# Copy new build
echo "📦 Deploying new frontend..."
rm -rf /opt/labcontrol/frontend/dist/*
cp -r /tmp/frontend-dist/* /opt/labcontrol/frontend/dist/

# Clear Nginx cache
echo "🧹 Clearing Nginx cache..."
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec nginx nginx -s reload

echo "✅ Frontend updated successfully!"
echo "🌐 Visit: https://lab.srv879400.hstgr.cloud:8443"

# Cleanup
rm -rf /tmp/frontend-dist
```

### Create Backup Script

Create `/opt/labcontrol/scripts/backup.sh`:

```bash
#!/bin/bash
# Database Backup Script

set -e

BACKUP_DIR="/opt/labcontrol/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/labcontrol_db_$DATE.sql"

echo "💾 Creating database backup..."

# Create backup directory if not exists
mkdir -p $BACKUP_DIR

# Backup database
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec -T db \
  pg_dump -U labcontrol_user labcontrol_db > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

echo "✅ Backup created: ${BACKUP_FILE}.gz"

# Keep only last 7 days of backups
find $BACKUP_DIR -name "labcontrol_db_*.sql.gz" -mtime +7 -delete

echo "🧹 Old backups cleaned up"
```

### View Logs Script

Create `/opt/labcontrol/scripts/logs.sh`:

```bash
#!/bin/bash
# View Application Logs

SERVICE=${1:-web}
LINES=${2:-50}

echo "📋 Viewing logs for $SERVICE (last $LINES lines)..."
echo "Available services: web, db, redis, nginx, celery_worker, celery_beat"
echo ""

cd /opt/labcontrol

case $1 in
  --follow|-f)
    docker compose -f docker-compose.prod.yml logs -f --tail=$LINES web
    ;;
  --all)
    docker compose -f docker-compose.prod.yml logs --tail=$LINES
    ;;
  *)
    docker compose -f docker-compose.prod.yml logs --tail=$LINES $SERVICE
    ;;
esac
```

### Quick Status Script

Create `/opt/labcontrol/scripts/status.sh`:

```bash
#!/bin/bash
# Check Application Status

echo "🔍 LabControl Status Check"
echo "=========================="
echo ""

cd /opt/labcontrol

echo "📦 Docker Containers:"
docker compose -f docker-compose.prod.yml ps
echo ""

echo "💾 Database:"
docker compose -f docker-compose.prod.yml exec db pg_isready -U labcontrol_user
echo ""

echo "🔴 Redis:"
docker compose -f docker-compose.prod.yml exec redis redis-cli ping
echo ""

echo "🌐 Application Health:"
curl -s https://lab.srv879400.hstgr.cloud:8443/health/ || echo "❌ Application not responding"
echo ""

echo "📊 Disk Usage:"
df -h /opt/labcontrol
echo ""

echo "💾 Latest Backups:"
ls -lht /opt/labcontrol/backups/ | head -5
```

### Create Demo Data Script

Already exists at `/opt/labcontrol/apps/users/management/commands/create_demo_data.py`

Run with:
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py create_demo_data
```

### Make Scripts Executable

```bash
chmod +x /opt/labcontrol/scripts/*.sh
```

### Usage Examples

```bash
# Update backend
/opt/labcontrol/scripts/update-backend.sh

# View logs (last 100 lines, following)
/opt/labcontrol/scripts/logs.sh -f

# View specific service logs
/opt/labcontrol/scripts/logs.sh nginx 200

# Create backup
/opt/labcontrol/scripts/backup.sh

# Check status
/opt/labcontrol/scripts/status.sh
```

---

## Next Steps

### 1. Move to Proper Domain

**Current:** `https://lab.srv879400.hstgr.cloud:8443`
**Target:** `https://lab.example.com`

**Steps:**
1. Purchase domain name
2. Point DNS A record to `72.60.137.226`
3. Obtain proper SSL certificate (Let's Encrypt):
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d lab.example.com
   ```
4. Update `.env.production`:
   ```
   DJANGO_ALLOWED_HOSTS=lab.example.com
   CSRF_TRUSTED_ORIGINS=https://lab.example.com
   CORS_ALLOWED_ORIGINS=https://lab.example.com
   FRONTEND_URL=https://lab.example.com
   ```
5. Update frontend `.env.production`:
   ```
   VITE_API_BASE_URL=https://lab.example.com/api/v1
   ```
6. Update Nginx configuration to use port 443 instead of 8443
7. Rebuild and redeploy

### 2. Setup Automated Backups

**Cron Job:**
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /opt/labcontrol/scripts/backup.sh >> /var/log/labcontrol-backup.log 2>&1

# Add weekly backup to remote storage (S3, etc.)
0 3 * * 0 /opt/labcontrol/scripts/backup-to-s3.sh >> /var/log/labcontrol-s3-backup.log 2>&1
```

### 3. Enable Email Notifications

**Gmail Setup:**
1. Enable 2-factor authentication
2. Generate App Password
3. Update `.env.production`:
   ```
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-app-password
   DEFAULT_FROM_EMAIL=LabControl <noreply@labcontrol.com>
   ```
4. Restart services

**Alternative:** Use SendGrid, Mailgun, or AWS SES for better deliverability

### 4. Create Staging Environment

**Staging Server:**
- Subdomain: `staging.lab.example.com`
- Separate database
- Same code, different environment

**Setup:**
1. Clone production setup
2. Create `config/settings/staging.py`
3. Use different `.env.staging`
4. Deploy to separate port or subdomain
5. Test all changes here before production

### 5. Setup Monitoring

**Options:**
- **Sentry** - Error tracking (already configured in settings)
- **Uptime Robot** - Uptime monitoring
- **Grafana + Prometheus** - Metrics and dashboards
- **New Relic** - APM

### 6. Implement CI/CD

**GitHub Actions Workflow:**
```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          password: ${{ secrets.SSH_PASSWORD }}
          script: |
            cd /opt/labcontrol
            git pull origin main
            /opt/labcontrol/scripts/update-backend.sh
```

### 7. Security Hardening

- [ ] Change default SSH port
- [ ] Disable root SSH login
- [ ] Setup firewall rules (ufw)
- [ ] Enable fail2ban for all services
- [ ] Implement rate limiting at Nginx level
- [ ] Regular security updates
- [ ] Setup intrusion detection (OSSEC, AIDE)

### 8. Performance Optimization

- [ ] Enable Redis persistence
- [ ] Setup PostgreSQL connection pooling (PgBouncer)
- [ ] Configure Nginx caching
- [ ] Enable Gzip compression
- [ ] Implement CDN for static files
- [ ] Database query optimization
- [ ] Add database indexes

---

## Known Issues

### Frontend Issues

#### 1. Background Image Not Covering Sides

**Location:** ResultsView.vue, ProfileView.vue

**Issue:** Background image doesn't cover full width on some screen sizes, leaving white gaps on sides.

**To Fix:**
```css
.background-decoration {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.background-decoration img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  min-width: 100vw;  /* Add this */
  min-height: 100vh; /* Add this */
}
```

#### 2. Browser Cache Issues

**Issue:** After deploying frontend updates, users see old cached version.

**Solution:** Add cache busting to Nginx config:
```nginx
location /assets/ {
    alias /usr/share/nginx/html/assets/;
    expires 1y;
    add_header Cache-Control "public, immutable";
}

location / {
    root /usr/share/nginx/html;
    try_files $uri $uri/ /index.html;
    expires -1;
    add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
}
```

---

## Troubleshooting

### Application Not Starting

```bash
# Check logs
/opt/labcontrol/scripts/logs.sh web 100

# Check all containers
docker compose -f /opt/labcontrol/docker-compose.prod.yml ps

# Restart all services
docker compose -f /opt/labcontrol/docker-compose.prod.yml restart
```

### Database Connection Issues

```bash
# Check database is running
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec db pg_isready

# Check database credentials
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec web env | grep DATABASE

# Connect to database
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec db psql -U labcontrol_user -d labcontrol_db
```

### Redis Issues

```bash
# Check Redis is running
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec redis redis-cli ping

# Flush cache
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec redis redis-cli FLUSHALL
```

### Nginx Issues

```bash
# Test configuration
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec nginx nginx -t

# Reload configuration
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec nginx nginx -s reload

# View Nginx logs
/opt/labcontrol/scripts/logs.sh nginx
```

### SSL Certificate Issues

```bash
# Check certificate expiry
openssl x509 -in /opt/labcontrol/nginx/ssl/cert.pem -noout -dates

# Regenerate self-signed certificate
cd /opt/labcontrol/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/C=AR/ST=BuenosAires/L=BuenosAires/O=LDM/CN=lab.srv879400.hstgr.cloud"

# Restart Nginx
docker compose -f /opt/labcontrol/docker-compose.prod.yml restart nginx
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Check disk space
df -h

# Check database size
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec db \
  psql -U labcontrol_user -d labcontrol_db -c \
  "SELECT pg_size_pretty(pg_database_size('labcontrol_db'));"

# Check slow queries
docker compose -f /opt/labcontrol/docker-compose.prod.yml exec db \
  psql -U labcontrol_user -d labcontrol_db -c \
  "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

---

## Production Checklist

Before going live with real users:

- [ ] Change all default passwords
- [ ] Setup proper domain with SSL
- [ ] Enable email notifications
- [ ] Setup automated backups
- [ ] Configure monitoring and alerting
- [ ] Implement proper logging
- [ ] Load testing
- [ ] Security audit
- [ ] GDPR compliance review (if applicable)
- [ ] Create user documentation
- [ ] Train support team
- [ ] Create incident response plan
- [ ] Setup staging environment
- [ ] Implement CI/CD pipeline

---

## Support and Maintenance

### Regular Maintenance Tasks

**Daily:**
- Monitor application health
- Check error logs
- Verify backups completed

**Weekly:**
- Review performance metrics
- Check disk space
- Update dependencies (if needed)

**Monthly:**
- Security updates
- Database optimization
- Review and rotate logs
- Test backup restoration

**Quarterly:**
- Full security audit
- Performance review
- Disaster recovery test
- Update documentation

---

## Contact and Resources

**Documentation:**
- Django: https://docs.djangoproject.com/
- Vue.js: https://vuejs.org/guide/
- Docker: https://docs.docker.com/

**Project Files:**
- Backend: `/Users/cevichesmac/Desktop/labcontrol/`
- Frontend: `/Users/cevichesmac/Desktop/labcontrol-frontend/`
- Server: `/opt/labcontrol/`

**Useful Commands:**
```bash
# SSH into server
ssh deploy@72.60.137.226

# View application
https://lab.srv879400.hstgr.cloud:8443

# Django admin
https://lab.srv879400.hstgr.cloud:8443/admin/

# API docs
https://lab.srv879400.hstgr.cloud:8443/api/v1/
```

---

**End of Document**
