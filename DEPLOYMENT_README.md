# LabControl - Quick Deployment Guide

This guide provides quick reference for deploying and managing LabControl in production.

## 📋 Prerequisites

- Hostinger VPS (Ubuntu 22.04 LTS, 4GB+ RAM)
- Domain name configured with DNS pointing to VPS
- SSH access to VPS

## 🚀 Quick Start Deployment

### 1. Initial VPS Setup (One-time)

```bash
# SSH into VPS
ssh root@YOUR_VPS_IP

# Update system
apt update && apt upgrade -y

# Run initial setup (follow DEPLOYMENT_PLAN.md for detailed steps)
# - Create deploy user
# - Configure SSH
# - Setup firewall (UFW)
# - Install fail2ban
# - Install Docker & Docker Compose
# - Install Nginx
```

### 2. Deploy Application

```bash
# Switch to deploy user
su - deploy

# Create application directory
sudo mkdir -p /opt/labcontrol
sudo chown deploy:deploy /opt/labcontrol
cd /opt/labcontrol

# Clone repository
git clone https://github.com/yourusername/labcontrol.git .

# Create production environment file
cp .env.production.template .env.production
nano .env.production
# Fill in all configuration values (see template comments)

# Build Vue.js frontend (from local machine first)
# On local machine:
cd /path/to/labcontrol-frontend
npm run build
rsync -avz dist/ deploy@YOUR_VPS_IP:/opt/labcontrol/frontend/dist/

# Back on VPS:
# Update Nginx configuration with your domain
nano nginx/conf.d/labcontrol.conf
# Replace 'lab.yourdomain.com' with your actual domain

# Build Docker images
docker compose -f docker-compose.prod.yml build

# Start database and redis
docker compose -f docker-compose.prod.yml up -d db redis

# Wait a few seconds, then run migrations
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate

# Create superuser
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser

# Collect static files
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput

# Start all services
docker compose -f docker-compose.prod.yml up -d

# Check logs
docker compose -f docker-compose.prod.yml logs -f
```

### 3. Configure SSL Certificate

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Stop Nginx container temporarily
docker compose -f docker-compose.prod.yml stop nginx

# Generate certificate
sudo certbot certonly --standalone \
    -d lab.yourdomain.com \
    -d www.lab.yourdomain.com \
    --email your-email@example.com \
    --agree-tos

# Copy certificates to Nginx
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/fullchain.pem /opt/labcontrol/nginx/ssl/
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/privkey.pem /opt/labcontrol/nginx/ssl/
sudo chown deploy:deploy /opt/labcontrol/nginx/ssl/*.pem

# Start Nginx
docker compose -f docker-compose.prod.yml up -d nginx
```

### 4. Setup Automated Backups

```bash
# Test backup script
source /opt/labcontrol/.env.production
sudo -E /opt/labcontrol/scripts/backup.sh

# Schedule daily backups (2 AM)
crontab -e
# Add this line:
0 2 * * * /bin/bash -c 'source /opt/labcontrol/.env.production && /opt/labcontrol/scripts/backup.sh' >> /opt/labcontrol/backups/logs/cron.log 2>&1
```

### 5. Setup Health Checks

```bash
# Configure health check
nano /opt/labcontrol/scripts/health_check.sh
# Update DOMAIN variable with your actual domain

# Schedule health checks (every 5 minutes)
crontab -e
# Add this line:
*/5 * * * * DOMAIN=https://lab.yourdomain.com /opt/labcontrol/scripts/health_check.sh >> /opt/labcontrol/logs/health.log 2>&1
```

## 🛠️ Daily Operations

### Using the Deployment Helper Script

```bash
cd /opt/labcontrol

# View all available commands
./scripts/deploy.sh help

# Common operations
./scripts/deploy.sh status     # Check container status
./scripts/deploy.sh logs       # View logs
./scripts/deploy.sh restart    # Restart services
./scripts/deploy.sh health     # Check health
./scripts/deploy.sh backup     # Run backup manually
```

### Manual Docker Compose Commands

```bash
cd /opt/labcontrol

# Start all services
docker compose -f docker-compose.prod.yml up -d

# Stop all services
docker compose -f docker-compose.prod.yml down

# View logs
docker compose -f docker-compose.prod.yml logs -f

# View logs for specific service
docker compose -f docker-compose.prod.yml logs -f web

# Restart a specific service
docker compose -f docker-compose.prod.yml restart web

# Check container status
docker compose -f docker-compose.prod.yml ps

# Run Django management command
docker compose -f docker-compose.prod.yml exec web python manage.py <command>

# Open Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Open database shell
docker compose -f docker-compose.prod.yml exec db psql -U labcontrol_user labcontrol_db
```

## 🔄 Updating the Application

```bash
cd /opt/labcontrol

# Use the automated update command
./scripts/deploy.sh update

# Or manually:
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml up -d
```

## 💾 Backup & Restore

### Create Backup

```bash
# Automated (scheduled via cron)
# Runs daily at 2 AM

# Manual backup
cd /opt/labcontrol
source .env.production
./scripts/backup.sh
```

### Restore from Backup

```bash
cd /opt/labcontrol

# List available backups
ls -lh backups/postgres/

# Restore database
./scripts/restore.sh backups/postgres/db_20260222_020000.sql.gz
```

## 🔍 Monitoring & Troubleshooting

### Check Service Health

```bash
# Using helper script
./scripts/deploy.sh health

# Check web service
curl -f https://lab.yourdomain.com/health/

# Check container logs
docker compose -f docker-compose.prod.yml logs web
docker compose -f docker-compose.prod.yml logs celery_worker
docker compose -f docker-compose.prod.yml logs db

# Check resource usage
docker stats

# Check disk space
df -h
du -sh /opt/labcontrol/*
```

### Common Issues

**Issue: Services won't start**
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs

# Check if ports are already in use
sudo netstat -tulpn | grep -E ':(80|443|5432|6379)'

# Restart Docker
sudo systemctl restart docker
```

**Issue: Database connection errors**
```bash
# Check if database is running
docker compose -f docker-compose.prod.yml ps db

# Check database logs
docker compose -f docker-compose.prod.yml logs db

# Test database connection
docker compose -f docker-compose.prod.yml exec db psql -U labcontrol_user -d labcontrol_db -c "SELECT 1;"
```

**Issue: SSL certificate errors**
```bash
# Check certificate expiry
sudo certbot certificates

# Renew certificates manually
sudo certbot renew

# Copy renewed certificates
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/*.pem /opt/labcontrol/nginx/ssl/
docker compose -f docker-compose.prod.yml restart nginx
```

**Issue: Out of disk space**
```bash
# Check disk usage
df -h

# Clean Docker images and volumes
docker system prune -a
docker volume prune

# Clean old backups
find /opt/labcontrol/backups -name "*.gz" -mtime +30 -delete
```

## 📊 Monitoring Logs

```bash
# Application logs
docker compose -f docker-compose.prod.yml logs -f web

# Nginx access logs
tail -f /opt/labcontrol/nginx/logs/labcontrol_access.log

# Nginx error logs
tail -f /opt/labcontrol/nginx/logs/labcontrol_error.log

# Backup logs
tail -f /opt/labcontrol/backups/logs/backup.log

# Health check logs
tail -f /opt/labcontrol/logs/health.log

# System logs
sudo tail -f /var/log/syslog

# Fail2ban logs
sudo tail -f /var/log/fail2ban.log
```

## 🔐 Security Checklist

- [ ] Firewall (UFW) is active
- [ ] fail2ban is running
- [ ] SSH root login disabled
- [ ] SSH password authentication disabled
- [ ] SSL/TLS certificates are valid
- [ ] All `.env.production` values are strong and unique
- [ ] Database password is strong
- [ ] Django SECRET_KEY is unique and secure
- [ ] Automated backups are running
- [ ] Backup offsite storage is configured
- [ ] Health checks are running
- [ ] System updates are applied regularly

## 📞 Emergency Contacts

- **VPS Provider**: Hostinger Support
- **Domain Registrar**: [Your registrar]
- **Admin Email**: [Your email]
- **Backup Storage**: [Your storage provider]

## 📚 Additional Resources

- Full deployment guide: `DEPLOYMENT_PLAN.md`
- Django production checklist: https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/
- Docker Compose reference: https://docs.docker.com/compose/
- Nginx configuration: https://nginx.org/en/docs/

---

**Last Updated**: 2026-02-22
**Version**: 1.0
