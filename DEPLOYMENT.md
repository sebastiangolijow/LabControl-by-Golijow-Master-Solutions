# LabControl Production Deployment Guide

**Last Updated**: March 22, 2026
**Environment**: Staging/Production
**Server**: Hostinger VPS

---

## 📋 Table of Contents

1. [Recent Updates & Fixes](#recent-updates--fixes)
2. [Infrastructure Overview](#infrastructure-overview)
3. [Technologies & Stack](#technologies--stack)
4. [Server Configuration](#server-configuration)
5. [Domain & DNS Setup](#domain--dns-setup)
6. [SSL Certificates](#ssl-certificates)
7. [Application Architecture](#application-architecture)
8. [Deployment Decisions](#deployment-decisions)
9. [FTP Server Configuration](#-ftp-server-configuration)
10. [LabWin Backup Ingestion Pipeline](#-labwin-backup-ingestion-pipeline)
11. [Updating the Application](#updating-the-application)
12. [Troubleshooting](#troubleshooting)

---

## 🔧 Recent Updates & Fixes

### March 22, 2026: SSL Certificate & Port Preservation Fix

**📦 Verified Working Backup Available**: `backups/2026-03-22-working-config/`

A complete backup of this working configuration has been saved. See [backups/INDEX.md](backups/INDEX.md) for details.

Quick restore if issues occur:
```bash
cd backups/2026-03-22-working-config
./restore.sh nginx    # Restore nginx config only (30 seconds)
./restore.sh env      # Restore environment variables (2-3 minutes)
./restore.sh full     # Full restore (5-10 minutes)
```

**Issue**: After certificate renewal, the staging app showed SSL certificate errors ("Not Secure" warning) and Django admin redirects were losing the `:8443` port.

**Root Causes Identified**:

1. **SSL Certificate Path Issue**:
   - Nginx config was pointing to old certificates in `./nginx/ssl/` (dated Feb 27, 2026)
   - Fresh Let's Encrypt certificates existed in `/etc/letsencrypt/live/` but weren't being used
   - After nginx restart, it loaded stale certificates causing SSL errors

2. **Django Admin Port Loss**:
   - Accessing `/django-admin` (no trailing slash) triggered Django redirect to `/django-admin/`
   - Django returned relative redirect: `Location: /django-admin/`
   - Nginx converted it to absolute URL but lost the `:8443` port
   - Browser redirect to `https://domain/django-admin/` (without port) caused SSL errors

**Fixes Applied**:

1. **SSL Certificate Fix** (commit `5e9091a`):
   - Updated `nginx/conf.d/labcontrol.conf` to use Let's Encrypt certificates directly:
     ```nginx
     ssl_certificate /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/fullchain.pem;
     ssl_certificate_key /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/privkey.pem;
     ```
   - Removed references to `./nginx/ssl/` directory
   - Now nginx always uses fresh, auto-renewed certificates

2. **Django Admin Port Preservation** (commit `9a4a283`):
   - Added nginx location block to handle `/django-admin` (no slash) redirect:
     ```nginx
     location = /django-admin {
         return 301 https://$http_host/django-admin/;
     }
     ```
   - Using `$http_host` variable preserves the original port from client request
   - Location block `/django-admin/` now uses `proxy_set_header Host $http_host;`

3. **Additional Improvements**:
   - Switched from `django_redis` to Django's built-in Redis cache backend
   - Fixed Dockerfile PATH for appuser (was `/root/.local`, now `/home/appuser/.local`)

**Result**:
- ✅ SSL certificates valid and auto-renewing
- ✅ Django admin accessible at `https://labmolecuar-portal-clientes-staging.com:8443/django-admin/`
- ✅ Profile pictures URLs include port: `https://...com:8443/media/profile_pictures/...`
- ✅ All redirects preserve `:8443` port

**Key Lesson**: When mounting Let's Encrypt certificates, always point nginx config directly to `/etc/letsencrypt/live/` to ensure auto-renewal works seamlessly.

---

## 🏗️ Infrastructure Overview

### Server Details
- **Provider**: Hostinger VPS
- **Server IP**: `72.60.137.226`
- **OS**: Ubuntu Linux
- **User**: `deploy@72.60.137.226` (password auth, used for **all** deployment operations — see [SSH Access](#ssh-access))

### Application Location
```
/opt/labcontrol/          # Main application directory
├── backend files         # Django application
├── frontend/dist/        # Built Vue.js frontend
├── nginx/               # Nginx configuration
├── .env.production      # Environment variables
└── docker-compose.prod.yml
```

---

## 🛠️ Technologies & Stack

### Backend
- **Framework**: Django 4.2
- **API**: Django REST Framework
- **Database**: PostgreSQL 15
- **Task Queue**: Celery + Redis
- **WSGI Server**: Gunicorn
- **Authentication**: JWT (djangorestframework-simplejwt)

### Frontend
- **Framework**: Vue.js 3 (Vite)
- **Build Tool**: Vite
- **Routing**: Vue Router
- **State Management**: Pinia

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Web Server**: Nginx (Alpine)
- **Reverse Proxy**: Nginx
- **SSL**: Let's Encrypt (Certbot)
- **Process Manager**: Docker Compose

### Additional Services
- **n8n**: Workflow automation (running on Traefik)
- **Traefik**: Reverse proxy for n8n (ports 80/443)

---

## 🖥️ Server Configuration

### Port Allocation

| Service | External Port | Internal Port | Purpose |
|---------|--------------|---------------|---------|
| LabControl HTTPS | 8443 | 443 | Main application (SSL) |
| Traefik HTTP | 80 | 80 | n8n (redirect to HTTPS) |
| Traefik HTTPS | 443 | 443 | n8n automation platform |

**Why port 8443?**
- Traefik (used by n8n) occupies ports 80/443
- To avoid conflicts, LabControl uses external port 8443
- Nginx internally still uses port 443 (SSL)
- Docker maps: `8443:443`

### Docker Containers

```bash
# View running containers
docker ps

# Expected containers:
# - labcontrol_nginx        (Port 8443->443)
# - labcontrol_web          (Django + Gunicorn)
# - labcontrol_db           (PostgreSQL)
# - labcontrol_redis        (Redis)
# - labcontrol_celery_worker
# - labcontrol_celery_beat
# - root-traefik-1          (Ports 80, 443)
# - root-n8n-1
```

---

## 🌐 Domain & DNS Setup

### Domain Information
- **Domain**: `labmolecuar-portal-clientes-staging.com`
- **Registrar**: Hostinger
- **DNS Provider**: Hostinger DNS

**Important**: Domain spelling is `labmolecuar` (without "l" in "molecular")

### DNS Records

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | @ | 72.60.137.226 | 14400 |
| A | www | 72.60.137.226 | 14400 |

**Nameservers** (Hostinger):
- `ns1.dns-parking.com`
- `ns2.dns-parking.com`

### DNS Propagation
- **Propagation Time**: 24-48 hours (typically faster)
- **Check Status**: https://dnschecker.org/
- **Test DNS**: `nslookup labmolecuar-portal-clientes-staging.com 8.8.8.8`

---

## 🔒 SSL Certificates

### Let's Encrypt Setup

**Certificate Details**:
- **Provider**: Let's Encrypt (free)
- **Tool**: Certbot
- **Domains Covered**:
  - `labmolecuar-portal-clientes-staging.com`
  - `www.labmolecuar-portal-clientes-staging.com`
- **Expiration**: 90 days (auto-renewal enabled)
- **Certificate Location**: `/etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/`

### Certificate Files
```bash
/etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/
├── fullchain.pem    # Full certificate chain (symlink to archive)
├── privkey.pem      # Private key (symlink to archive)
├── cert.pem         # Certificate only (symlink to archive)
└── chain.pem        # Intermediate certificates (symlink to archive)
```

**Important**: These are symlinks that automatically point to the latest certificate version in `/etc/letsencrypt/archive/`. When certbot renews, it creates new files and updates these symlinks.

### Nginx Configuration

The nginx config **must** point directly to Let's Encrypt certificates:

```nginx
# In nginx/conf.d/labcontrol.conf
ssl_certificate /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/privkey.pem;
```

**DO NOT** use `./nginx/ssl/` directory - those files are not auto-updated and will become stale.

### How Certificates Were Obtained

1. **Stop Traefik** (to free port 80):
   ```bash
   docker stop root-traefik-1
   ```

2. **Generate Certificate**:
   ```bash
   sudo certbot certonly --standalone \
     -d labmolecuar-portal-clientes-staging.com \
     -d www.labmolecuar-portal-clientes-staging.com \
     --email sebastian.golijow@gmail.com \
     --agree-tos \
     --non-interactive
   ```

3. **Restart Traefik**:
   ```bash
   docker start root-traefik-1
   ```

4. **Restart Nginx** to load certificates:
   ```bash
   cd /opt/labcontrol
   docker compose -f docker-compose.prod.yml restart nginx
   ```

### Certificate Renewal

Certbot automatically creates a systemd timer for renewal. Verify with:
```bash
sudo systemctl list-timers | grep certbot
```

**Manual renewal** (if needed or to force renewal):
```bash
# 1. Stop Traefik temporarily (to free port 80)
docker stop root-traefik-1

# 2. Renew certificates (use --force-renewal to renew before expiration)
sudo certbot renew --force-renewal

# 3. Restart Traefik
docker start root-traefik-1

# 4. Restart Nginx to load new certificates
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml restart nginx

# 5. Verify new certificate is loaded
echo | openssl s_client -connect labmolecuar-portal-clientes-staging.com:8443 \
  -servername labmolecuar-portal-clientes-staging.com 2>/dev/null | \
  openssl x509 -noout -dates
```

**Check certificate expiration**:
```bash
sudo certbot certificates
```

**Important**: Since nginx config points directly to `/etc/letsencrypt/live/`, you only need to restart nginx after renewal. The symlinks are automatically updated by certbot.

---

## 🏛️ Application Architecture

### Container Network

```
┌─────────────────────────────────────────────────────────┐
│                    Internet (HTTPS)                     │
│          https://labmolecuar-portal-...:8443            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │  Nginx (Alpine) │  Port 8443->443 (SSL)
            │  Reverse Proxy  │  /etc/letsencrypt mounted
            └────────┬────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   /api/        /media/      / (root)
   Django       Media        Vue.js
                Files        SPA
        │            │
        ▼            │
┌──────────────┐    │
│   Django +   │    │
│   Gunicorn   │◄───┘
│   (port 8000)│
└──────┬───────┘
       │
   ┌───┴────┬──────────┐
   ▼        ▼          ▼
┌─────┐  ┌─────┐  ┌────────┐
│ DB  │  │Redis│  │ Celery │
│(PG) │  │     │  │Workers │
└─────┘  └─────┘  └────────┘
```

### File Upload Flow (Profile Pictures)

1. **Frontend** sends multipart/form-data to `/api/v1/auth/user/`
2. **Nginx** proxies to Django with `$http_host` header (includes port `:8443`)
3. **Django** receives `Host: labmolecuar-portal-clientes-staging.com:8443`
4. **Django** saves file to `/app/media/profile_pictures/`
5. **Django** returns URL: `https://labmolecuar-portal-clientes-staging.com:8443/media/profile_pictures/xxx.jpeg`
6. **Nginx** serves file from mounted volume `/app/media/`

### Port Preservation Strategy

**Why port preservation is critical**:
- External port `8443` must appear in all URLs (profile pictures, API responses, redirects)
- Django needs to know the original port to generate correct absolute URLs
- Without port in URLs, browser connects to port `443` (wrong port, SSL errors)

**How port is preserved**:

1. **API Endpoints** (`/api/`, `/media/`):
   ```nginx
   location /api/ {
       proxy_set_header Host $http_host;  # Passes "domain:8443" to Django
       proxy_pass http://django_app;
   }
   ```

2. **Django Admin Redirect** (`/django-admin` → `/django-admin/`):
   ```nginx
   # Handle trailing slash redirect in nginx (not Django)
   location = /django-admin {
       return 301 https://$http_host/django-admin/;  # Preserves port
   }

   location /django-admin/ {
       proxy_set_header Host $http_host;  # Passes port to Django
       proxy_pass http://django_app;
   }
   ```

**Key nginx variable**: `$http_host` = original `Host` header from client = `domain:8443`

---

## 📝 Deployment Decisions

### 1. Port 8443 vs Standard HTTPS (443)

**Decision**: Use port 8443 for LabControl

**Reason**:
- n8n workflow automation requires Traefik on ports 80/443
- Both services need to run simultaneously
- Changing n8n configuration would be complex

**Trade-off**: Users must include `:8443` in URL
**Future**: Migrate n8n to subdomain and reclaim port 443

### 2. Nginx vs Traefik for LabControl

**Decision**: Use Nginx for LabControl

**Reason**:
- LabControl already configured with Nginx
- Traefik is dedicated to n8n
- Nginx is simpler for static file serving
- Less complex than configuring Traefik routes

### 3. Self-Signed vs Let's Encrypt Certificates

**Decision**: Let's Encrypt

**Reason**:
- Free and trusted by all browsers
- Automatic renewal
- No "Not Secure" warnings
- Industry standard

### 4. Docker Volumes vs Bind Mounts

**Decision**: Mix of both

**Volumes** (Docker-managed):
- `postgres_data`: Database persistence
- `redis_data`: Cache persistence
- `labcontrol_static`: Django static files
- `labcontrol_media`: User uploads

**Bind Mounts** (Direct paths):
- `./frontend/dist`: Frontend build files
- `./nginx/conf.d`: Nginx configuration
- `/etc/letsencrypt`: SSL certificates

**Reason**: Volumes for data, bind mounts for easy updates

### 5. Environment Variables Management

**Decision**: `.env.production` file on server

**Reason**:
- Secrets not committed to git
- Easy to update without rebuilding
- Standard Django practice

**Security**: File permissions set to `600` (owner read/write only)

### 6. FTP Server for LabWin PDF Results

**Decision**: vsftpd on the VPS host, accessed by Docker containers via `host.docker.internal`

**Reason**:
- LabWin exports PDF result files per protocol (e.g. `100001.pdf`)
- The lab team configures LabWin to upload PDFs to this FTP server
- A Celery task (`fetch_ftp_pdfs`) connects to the FTP, matches filenames to `Study.sample_id`, and attaches the PDF to the study

---

## 📡 FTP Server Configuration

### Overview

The VPS runs a vsftpd FTP server that receives PDF result files from LabWin. Docker containers connect to it via `host.docker.internal`.

### FTP Credentials (for lab team)

| Setting | Value |
|---------|-------|
| **Host** | `72.60.137.226` |
| **Port** | `21` |
| **User** | `labwin_ftp` |
| **Password** | *See 1Password → "LabControl LabWin FTP user". Mirrored on the server in `.env.production` as `LABWIN_FTP_PASSWORD` and in `/etc/vsftpd.userlist`.* |
| **Directory** | `/results` |
| **Protocol** | FTP (plain, no TLS) |
| **Passive Mode** | Yes (ports 30000-30100) |

> When sharing the password with the lab team, send it via 1Password share-link or another out-of-band channel — never paste it into Slack/email.

### File Naming Convention

PDFs must be named `{NUMERO}.pdf` where `{NUMERO}` is the LabWin protocol number (NUMERO_FLD from DETERS table).

Examples: `100001.pdf`, `100002.pdf`, `100003.pdf`

### Server Setup (already configured)

```bash
# vsftpd installed and running
sudo systemctl status vsftpd

# FTP user
user: labwin_ftp
home: /home/labwin_ftp
upload dir: /home/labwin_ftp/results/
shell: /usr/sbin/nologin (FTP only, no SSH)

# Config file: /etc/vsftpd.conf
# Key settings:
#   chroot_local_user=YES (user locked to home dir)
#   pasv_enable=YES (passive mode for NAT/firewall)
#   pasv_min_port=30000, pasv_max_port=30100
#   pasv_address=72.60.137.226
#   userlist_enable=YES (whitelist in /etc/vsftpd.userlist)

# Firewall ports opened:
#   21/tcp (FTP control)
#   30000:30100/tcp (passive data)
```

### Docker Integration

`docker-compose.prod.yml` has `extra_hosts: ["host.docker.internal:host-gateway"]` on `web` and `celery_worker` services.

`.env.production` settings (see `.env.production.template` for the canonical schema):
```env
LABWIN_FTP_USE_MOCK=False
LABWIN_FTP_HOST=host.docker.internal
LABWIN_FTP_PORT=21
LABWIN_FTP_USER=labwin_ftp
LABWIN_FTP_PASSWORD=<from 1Password: "LabControl LabWin FTP user">
LABWIN_FTP_DIRECTORY=/results
LABWIN_FTP_USE_TLS=False
```

### Testing FTP Manually

```bash
# Pre-requisite: export the FTP password from 1Password
export LABWIN_FTP_PASSWORD='...'   # from 1Password → "LabControl LabWin FTP user"

# From local machine
ftp 72.60.137.226
# Login: labwin_ftp / $LABWIN_FTP_PASSWORD
# cd results
# put 100001.pdf

# From inside Docker container (uses the same env var Django reads)
docker compose -f docker-compose.prod.yml exec web python -c "
import os
from ftplib import FTP
ftp = FTP()
ftp.connect('host.docker.internal', 21)
ftp.login('labwin_ftp', os.environ['LABWIN_FTP_PASSWORD'])
ftp.cwd('/results')
print(ftp.nlst())
ftp.quit()
"
```

### Triggering PDF Fetch

- **UI**: Click the green PDF sync button on the Results page (admin only)
- **API**: `POST /api/v1/labwin-sync/fetch-pdfs/`
- **CLI**: `python manage.py fetch_ftp_pdfs [--delete] [--cleanup]`
- **Scheduled**: Can be added to Celery Beat for automatic fetching

---

## 💾 LabWin Backup Ingestion Pipeline

### Why This Exists

The lab's PC running LabWin (Firebird 2.5) has **no public IP** and cannot accept inbound connections. The VPS therefore cannot pull data from the Firebird service directly. Instead, the lab PC **pushes** a nightly backup to the VPS via SFTP, and the VPS restores it into a local Firebird container that the existing `labwin_sync` connector reads from.

This pipeline is what makes `LABWIN_USE_MOCK=False` viable in production.

### Architecture Summary

```
PC Lab ─[02:00 AM  gbak + gzip + SFTP]─► VPS /srv/labwin_backups/incoming/
                                              │
                                              │ (Celery Beat 04:00 AM)
                                              ▼
                                    import_uploaded_backup task
                                              │
                                              ├─► gbak -r → firebird container
                                              └─► sync_labwin_results()
```

See **[`LABWIN_BACKUP_PIPELINE.md`](./LABWIN_BACKUP_PIPELINE.md)** for the complete design doc: component-by-component implementation plan, security considerations, failure modes, and phased rollout.

### SFTP Credentials (for lab team)

| Setting | Value |
|---------|-------|
| **Host** | `72.60.137.226` |
| **Port** | `22` |
| **User** | `backup_user` |
| **Auth** | SSH key (no password) |
| **Upload dir** | `/incoming/` (chroot) |
| **Protocol** | SFTP |

**Note:** Distinct from the FTP credentials above. FTP is for PDF results pull-from-lab (Phase 13); SFTP is for DB backups push-from-lab (this section).

### VPS Directory Layout

```
/srv/labwin_backups/
├── incoming/     ← backup_user SFTP chroot (writable)
├── processed/    ← successfully ingested backups (rotated > 30 days)
└── failed/       ← backups that failed to restore (kept for debugging)
```

### Docker Services

A new `firebird` service is added to `docker-compose.prod.yml` to host the restored database:

```yaml
firebird:
  image: jacobalberty/firebird:2.5-ss
  container_name: labcontrol_firebird
  volumes:
    - firebird_data:/firebird/data
    - /srv/labwin_backups/incoming:/backups/incoming:ro
  networks: [labcontrol_net]
  # Not exposed to host — only reachable via docker network
```

`.env.production` additions:
```env
LABWIN_USE_MOCK=False
LABWIN_FDB_HOST=firebird              # docker service name
LABWIN_FDB_PORT=3050
LABWIN_FDB_DATABASE=/firebird/data/BASEDAT.FDB
LABWIN_FDB_USER=SYSDBA
LABWIN_FDB_PASSWORD=<see secrets vault>
FIREBIRD_SYSDBA_PASSWORD=<same as above>
```

### Triggering Backup Ingestion

- **Scheduled**: Celery Beat runs `import_uploaded_backup` at 04:00 AM daily
- **CLI manual**: `python manage.py import_backup [--file PATH] [--restore-only] [--sync-only]`
- **Admin UI**: (future) button in Django Admin → SyncLog view

### Status

**Current state:** Designed but not yet implemented. The LabControl codebase still runs with `LABWIN_USE_MOCK=True` in production.

**To enable:** Follow the phased plan (A through F) in `LABWIN_BACKUP_PIPELINE.md`. Estimated effort: 3–5 days of dev + a 2-hour onsite visit to the lab.

---

## 🔄 Updating the Application

### Frontend Updates

When you make changes to the Vue.js frontend:

```bash
# 1. LOCAL: Make your changes in /Desktop/labcontrol-frontend/src/

# 2. LOCAL: Build the frontend
cd /Users/cevichesmac/Desktop/labcontrol-frontend
npm run build

# 3. LOCAL: Copy built files to server
sshpass -p "$DEPLOY_SSH_PASSWORD" scp -r dist/* deploy@72.60.137.226:/opt/labcontrol/frontend/dist/

# 4. SERVER: Restart Nginx to clear cache
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml restart nginx"

# 5. BROWSER: Hard refresh (Ctrl+Shift+R) or open incognito to see changes
```

**Alternative** (if scp is slow):
```bash
# Create tarball locally
cd /Users/cevichesmac/Desktop/labcontrol-frontend
tar -czf dist.tar.gz dist/

# Upload tarball
sshpass -p "$DEPLOY_SSH_PASSWORD" scp dist.tar.gz deploy@72.60.137.226:/tmp/

# Extract on server
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
cd /opt/labcontrol/frontend
rm -rf dist/*
tar -xzf /tmp/dist.tar.gz --strip-components=1
rm /tmp/dist.tar.gz
exit

# Restart nginx
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml restart nginx"
```

### Backend Updates

When you make changes to Django backend code:

```bash
# 1. LOCAL: Make changes in /Desktop/labcontrol/apps/ or config/

# 2. LOCAL: Test locally first
cd /Users/cevichesmac/Desktop/labcontrol
make test

# 3. LOCAL: If database schema changed, create migration
python manage.py makemigrations

# 4. LOCAL: Copy updated files to server (be selective!)
# Copy specific app:
sshpass -p "$DEPLOY_SSH_PASSWORD" scp -r apps/users/* deploy@72.60.137.226:/opt/labcontrol/apps/users/

# Copy multiple files:
sshpass -p "$DEPLOY_SSH_PASSWORD" scp apps/users/views.py apps/users/serializers.py deploy@72.60.137.226:/opt/labcontrol/apps/users/

# 5. SERVER: Rebuild and restart containers
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
cd /opt/labcontrol

# Rebuild the image (if you changed requirements.txt or Dockerfile)
docker compose -f docker-compose.prod.yml build web

# Run migrations (if you created new migrations)
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate

# Restart all backend services
docker compose -f docker-compose.prod.yml restart web celery_worker celery_beat

# 6. Verify logs
docker logs labcontrol_web --tail 50
```

### Environment Variable Updates

When you update `.env.production`:

```bash
# 1. LOCAL: Update local file
# Edit /Users/cevichesmac/Desktop/labcontrol/.env.production

# 2. LOCAL: Copy to server
sshpass -p "$DEPLOY_SSH_PASSWORD" scp .env.production deploy@72.60.137.226:/opt/labcontrol/

# 3. SERVER: Recreate containers (restart doesn't reload env vars!)
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml stop web celery_worker
docker compose -f docker-compose.prod.yml rm -f web celery_worker
docker compose -f docker-compose.prod.yml up -d web celery_worker

# 4. Verify env vars loaded
docker exec labcontrol_web env | grep DJANGO_
```

### Nginx Configuration Updates

When you update Nginx config:

```bash
# 1. LOCAL: Edit configuration
# Edit /Users/cevichesmac/Desktop/labcontrol/nginx/conf.d/labcontrol.conf

# 2. LOCAL: Copy to server and restart Nginx
sshpass -p "$DEPLOY_SSH_PASSWORD" scp \
  /Users/cevichesmac/Desktop/labcontrol/nginx/conf.d/labcontrol.conf \
  deploy@72.60.137.226:/opt/labcontrol/nginx/conf.d/labcontrol.conf

sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
  "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml restart nginx"

# 3. Verify nginx restarted successfully
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
  "docker logs labcontrol_nginx --tail 20"

# 4. Test configuration (optional)
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
  "docker exec labcontrol_nginx nginx -t"
```

### Full Application Redeployment

If you need to redeploy everything:

```bash
# 1. SERVER: Backup database first!
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
docker exec labcontrol_db pg_dump -U labcontrol_user labcontrol_db > /tmp/backup.sql

# 2. LOCAL: Build frontend
cd /Users/cevichesmac/Desktop/labcontrol-frontend
npm run build

# 3. LOCAL: Copy everything to server
cd /Users/cevichesmac/Desktop/labcontrol
sshpass -p "$DEPLOY_SSH_PASSWORD" rsync -avz --exclude 'node_modules' --exclude '.git' --exclude '__pycache__' --exclude '.env.production' \
  . deploy@72.60.137.226:/opt/labcontrol/

cd /Users/cevichesmac/Desktop/labcontrol-frontend
sshpass -p "$DEPLOY_SSH_PASSWORD" rsync -avz dist/ deploy@72.60.137.226:/opt/labcontrol/frontend/dist/

# 4. SERVER: Rebuild and restart
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
```

---

## 🔍 Troubleshooting

### Common Issues

#### 1. Changes Not Appearing in Browser

**Symptoms**: Updated code not visible in browser

**Solutions**:
```bash
# Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
# Or open incognito/private window

# Restart Nginx
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "docker compose -f /opt/labcontrol/docker-compose.prod.yml restart nginx"

# Check if files were actually updated
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "ls -la /opt/labcontrol/frontend/dist/"
```

#### 2. Environment Variables Not Loading

**Symptoms**: `DisallowedHost`, missing config

**Solution**:
```bash
# Restart doesn't reload env vars - must recreate!
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml stop web
docker compose -f docker-compose.prod.yml rm -f web
docker compose -f docker-compose.prod.yml up -d web
```

#### 3. Port 8443 Already in Use

**Symptoms**: Cannot start Nginx container

**Solution**:
```bash
# Find what's using port 8443
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "sudo lsof -i :8443"

# If it's a stuck container
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "docker ps -a | grep 8443"
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "docker stop <container_id>"
```

#### 4. SSL Certificate Expired or Invalid

**Symptoms**: Browser shows certificate error ("Not Secure", `NET::ERR_CERT_AUTHORITY_INVALID`)

**Solutions**:

1. **Check certificate expiration**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "sudo certbot certificates"

   # Or check what nginx is actually serving
   echo | openssl s_client -connect labmolecuar-portal-clientes-staging.com:8443 \
     -servername labmolecuar-portal-clientes-staging.com 2>/dev/null | \
     openssl x509 -noout -dates
   ```

2. **Verify nginx is using correct certificate path**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "grep ssl_certificate /opt/labcontrol/nginx/conf.d/labcontrol.conf"

   # Should show:
   # ssl_certificate /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/fullchain.pem;
   # ssl_certificate_key /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/privkey.pem;
   ```

3. **Check certificate files inside nginx container**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "docker exec labcontrol_nginx ls -la /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/"

   # Files should be recent (check dates)
   ```

4. **Renew certificate**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226

   # Stop Traefik to free port 80
   docker stop root-traefik-1

   # Renew certificate
   sudo certbot renew --force-renewal

   # Restart Traefik
   docker start root-traefik-1

   # Restart Nginx to load new certificates
   cd /opt/labcontrol
   docker compose -f docker-compose.prod.yml restart nginx

   # Verify
   docker logs labcontrol_nginx --tail 20
   ```

**Common Issue**: If nginx config points to `./nginx/ssl/` instead of `/etc/letsencrypt/live/`, certificates won't auto-update. See "Recent Updates & Fixes" section for details.

#### 5. Database Connection Issues

**Symptoms**: Cannot connect to database

**Solution**:
```bash
# Check if database container is running
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "docker ps | grep labcontrol_db"

# Check database logs
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "docker logs labcontrol_db --tail 50"

# Test database connection
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
docker exec -it labcontrol_db psql -U labcontrol_user -d labcontrol_db
# Should open PostgreSQL prompt
\q  # to exit
```

#### 6. Media Files (Profile Pictures) Not Accessible

**Symptoms**:
- 403 or 404 errors on media URLs
- Media URLs missing port `:8443`
- Profile pictures show as broken images

**Checklist**:

1. **Verify port is in media URLs**:
   ```bash
   # Check profile picture URL in API response
   # Should be: https://labmolecuar-portal-clientes-staging.com:8443/media/...
   # NOT: https://labmolecuar-portal-clientes-staging.com/media/...
   ```

2. **Verify Nginx uses $http_host header**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "grep -A 5 'location /api/' /opt/labcontrol/nginx/conf.d/labcontrol.conf"

   # Should show: proxy_set_header Host $http_host;
   # NOT: proxy_set_header Host $host;
   ```

3. **Verify media volume is mounted**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "docker exec labcontrol_nginx ls -la /app/media/"
   ```

4. **Verify files exist on server**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "docker exec labcontrol_web ls -la /app/media/profile_pictures/"
   ```

5. **Check nginx logs**:
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "docker logs labcontrol_nginx --tail 50 | grep media"
   ```

**See Also**: "Port Preservation Strategy" section for details on how port `:8443` is maintained in URLs.

#### 7. Django Admin Redirect Loses Port

**Symptoms**:
- Accessing `https://domain:8443/django-admin` redirects to `https://domain/django-admin/` (port missing)
- Browser shows SSL error after redirect

**Root Cause**: Django returns relative redirect `Location: /django-admin/` which nginx converts to absolute URL but loses port.

**Solution**:

1. **Verify nginx has location block for /django-admin** (no trailing slash):
   ```bash
   sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 \
     "grep -A 3 'location = /django-admin' /opt/labcontrol/nginx/conf.d/labcontrol.conf"

   # Should show:
   # location = /django-admin {
   #     return 301 https://$http_host/django-admin/;
   # }
   ```

2. **If missing, update nginx config**:
   - Edit local file `/Users/cevichesmac/Desktop/labcontrol/nginx/conf.d/labcontrol.conf`
   - Add the location block above
   - Deploy using the "Nginx Configuration Updates" procedure

3. **Test the redirect**:
   ```bash
   curl -I https://labmolecuar-portal-clientes-staging.com:8443/django-admin
   # Location header should include :8443
   ```

**See Also**: "Recent Updates & Fixes" section for detailed explanation.

---

## 📞 Quick Reference

### Important URLs

| Service | URL |
|---------|-----|
| Application | https://labmolecuar-portal-clientes-staging.com:8443 |
| Django Admin | https://labmolecuar-portal-clientes-staging.com:8443/django-admin/ |
| API Root | https://labmolecuar-portal-clientes-staging.com:8443/api/v1/ |
| n8n (Traefik) | https://72.60.137.226 |

**Note**: Django admin is at `/django-admin/` (not `/admin/`) as configured by `ADMIN_URL` environment variable.

### SSH Access

All deployment operations use the **`deploy`** user. There is no separate root SSH workflow — `deploy` has `sudo` for tasks that need it (e.g. `certbot renew`).

#### Where the password lives

The `deploy` SSH password is **not** stored in any file in this repo (including `.env.production`). It lives in:

- **Team 1Password vault** → entry name **"LabControl VPS deploy user"**
- (Reference noted in `.env.production.template` under "Deployment operator secrets")

Operators should pull it from 1Password and export it in their shell:

```bash
# Once per shell session
export DEPLOY_SSH_PASSWORD='...'   # from 1Password

# Or, if you use 1Password CLI:
export DEPLOY_SSH_PASSWORD=$(op read "op://Engineering/LabControl VPS deploy user/password")
```

After exporting, every `sshpass -p "$DEPLOY_SSH_PASSWORD" …` snippet in this guide works as-is.

```bash
# Interactive shell (will prompt for the password unless you pre-export it)
ssh deploy@72.60.137.226

# Automated / scripted (recommended for all deploy commands in this guide)
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226 "command"
sshpass -p "$DEPLOY_SSH_PASSWORD" scp local_file deploy@72.60.137.226:/remote/path
```

> **Future hardening**: switch `deploy` to SSH key auth and remove password access entirely. The `sshpass` workflow is a leftover from initial bring-up.

### Docker Commands

```bash
# View all containers
docker ps -a

# View logs
docker logs labcontrol_web --tail 50 -f
docker logs labcontrol_nginx --tail 30

# Enter container shell
docker exec -it labcontrol_web bash
docker exec -it labcontrol_db psql -U labcontrol_user -d labcontrol_db

# Restart services
docker compose -f docker-compose.prod.yml restart web
docker compose -f docker-compose.prod.yml restart nginx

# View docker compose status
docker compose -f docker-compose.prod.yml ps
```

### Database Access

```bash
# Connect to database
sshpass -p "$DEPLOY_SSH_PASSWORD" ssh deploy@72.60.137.226
docker exec -it labcontrol_db psql -U labcontrol_user -d labcontrol_db

# Backup database
docker exec labcontrol_db pg_dump -U labcontrol_user labcontrol_db > backup_$(date +%Y%m%d).sql

# Restore database
docker exec -i labcontrol_db psql -U labcontrol_user -d labcontrol_db < backup.sql
```

---

## 🎯 Next Steps

### Future Improvements

1. **Remove Port 8443**
   - Migrate n8n to subdomain (e.g., `n8n.labmolecuar...`)
   - Reconfigure Traefik for subdomain routing
   - Move LabControl to standard port 443

2. **Setup Automated Backups**
   - Create cron job for database backups
   - Upload backups to S3-compatible storage
   - Configure retention policy

3. **Monitoring & Alerts**
   - Setup health checks
   - Configure email alerts for downtime
   - Monitor disk space and resource usage

4. **Performance Optimization**
   - Implement Redis caching for API responses
   - Enable Gzip compression in Nginx
   - Optimize background images (see next section)

---

**Document Version**: 3.0
**Maintained By**: Development Team
**Last Reviewed**: April 18, 2026

## 📜 Change Log

### Version 3.0 - April 18, 2026
- Added FTP Server Configuration section with credentials and setup details
- Added Docker `extra_hosts` integration for container-to-host FTP access
- Added FTP testing and triggering instructions
- Updated deployment decision #6 for FTP architecture

### Version 2.0 - March 22, 2026
- Added "Recent Updates & Fixes" section documenting SSL certificate and port preservation fixes
- Updated SSL certificate paths to use `/etc/letsencrypt/live/` directly
- Added "Port Preservation Strategy" section explaining `$http_host` usage
- Updated Django Admin URL from `/admin` to `/django-admin/`
- Added sshpass commands for automated deployments
- Enhanced troubleshooting sections with port-related issues
- Added certificate renewal verification steps
- Documented deploy user password for automated deployments

### Version 1.0 - March 14, 2026
- Initial deployment guide
- Infrastructure overview and stack documentation
- SSL setup with Let's Encrypt
- Basic deployment procedures
