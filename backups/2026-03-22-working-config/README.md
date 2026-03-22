# LabControl Configuration Backup - March 22, 2026

**Status**: ✅ VERIFIED WORKING CONFIGURATION
**Date**: March 22, 2026
**Git Commit**: `e78c0e00461a6927085ff19552de1870a19d1624`

---

## 🎯 What's Working

This backup represents a **fully functional configuration** with the following verified features:

### ✅ SSL Certificate
- Valid Let's Encrypt certificate
- No browser warnings
- Auto-renewal configured
- Certificate path: `/etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/`

### ✅ Port Preservation (:8443)
- Django admin redirect: `https://domain:8443/django-admin/` ✅
- Profile picture URLs: `https://domain:8443/media/profile_pictures/xxx.png` ✅
- All API responses include port `:8443` ✅

### ✅ All Services Running
- Frontend: Vue.js app loading correctly
- Backend: Django + Gunicorn responding
- Database: PostgreSQL connected
- Cache: Redis working
- Celery: Background tasks processing
- Nginx: Reverse proxy with SSL

---

## 📦 Backup Contents

```
backups/2026-03-22-working-config/
├── README.md                      # This file
├── GIT_COMMIT.txt                 # Git commit hash for reference
├── labcontrol.conf                # Nginx configuration (CRITICAL)
├── docker-compose.prod.yml        # Docker Compose configuration
├── .env.production.backup         # Environment variables (with secrets)
└── VERIFICATION.txt               # Test results (generated below)
```

---

## 🔑 Key Configuration Highlights

### Nginx Configuration (`labcontrol.conf`)

**SSL Certificates** (pointing to Let's Encrypt):
```nginx
ssl_certificate /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/privkey.pem;
```

**Port Preservation** (all proxy locations use `$http_host`):
```nginx
location /api/ {
    proxy_set_header Host $http_host;  # Preserves port :8443
}

location /api/v1/auth/ {
    proxy_set_header Host $http_host;
}

location /django-admin/ {
    proxy_set_header Host $http_host;
}
```

**Django Admin Redirect** (handled by nginx to preserve port):
```nginx
location = /django-admin {
    return 301 https://$http_host/django-admin/;  # Preserves port
}
```

### Environment Variables

Key settings in `.env.production.backup`:
- `ADMIN_URL=django-admin/`
- `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,72.60.137.226,labmolecuar-portal-clients-staging.com`
- `FRONTEND_URL=https://labmolecuar-portal-clientes-staging.com:8443`
- SSL certificates pointing to Let's Encrypt

---

## 🔄 How to Restore This Configuration

### Option 1: Restore Nginx Config Only (Quick Fix)

If only nginx is broken:

```bash
# 1. Copy backup to server
sshpass -p '39872327Seba.' scp \
  backups/2026-03-22-working-config/labcontrol.conf \
  deploy@72.60.137.226:/opt/labcontrol/nginx/conf.d/labcontrol.conf

# 2. Restart nginx
sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
  "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml restart nginx"

# 3. Verify
curl -I https://labmolecuar-portal-clientes-staging.com:8443/
```

### Option 2: Restore Environment Variables

If environment variables are corrupted:

```bash
# 1. Copy backup to server
sshpass -p '39872327Seba.' scp \
  backups/2026-03-22-working-config/.env.production.backup \
  deploy@72.60.137.226:/opt/labcontrol/.env.production

# 2. Recreate containers (restart doesn't reload env vars!)
sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
  "cd /opt/labcontrol && \
   docker compose -f docker-compose.prod.yml stop web celery_worker && \
   docker compose -f docker-compose.prod.yml rm -f web celery_worker && \
   docker compose -f docker-compose.prod.yml up -d"
```

### Option 3: Full Restore (Nuclear Option)

If everything is broken:

```bash
# 1. Checkout the exact git commit
cd /Users/cevichesmac/Desktop/labcontrol
git checkout e78c0e00461a6927085ff19552de1870a19d1624

# 2. Copy all backup files to server
sshpass -p '39872327Seba.' scp \
  backups/2026-03-22-working-config/labcontrol.conf \
  deploy@72.60.137.226:/opt/labcontrol/nginx/conf.d/

sshpass -p '39872327Seba.' scp \
  backups/2026-03-22-working-config/docker-compose.prod.yml \
  deploy@72.60.137.226:/opt/labcontrol/

sshpass -p '39872327Seba.' scp \
  backups/2026-03-22-working-config/.env.production.backup \
  deploy@72.60.137.226:/opt/labcontrol/.env.production

# 3. Rebuild and restart all services
sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
  "cd /opt/labcontrol && \
   docker compose -f docker-compose.prod.yml down && \
   docker compose -f docker-compose.prod.yml up -d --build"

# 4. Return to main branch
git checkout main
```

---

## ✅ Verification Checklist

After restoring, verify these items:

```bash
# 1. SSL Certificate
curl -I https://labmolecuar-portal-clientes-staging.com:8443/
# Should return HTTP/2 200 with no SSL errors

# 2. Django Admin Redirect
curl -I https://labmolecuar-portal-clientes-staging.com:8443/django-admin
# Location header should include :8443

# 3. Frontend Loading
# Open browser: https://labmolecuar-portal-clientes-staging.com:8443
# Should load without SSL warnings

# 4. Django Admin Access
# Open browser: https://labmolecuar-portal-clientes-staging.com:8443/django-admin/
# Should load admin login page

# 5. Profile Picture Upload
# Login → Profile → Upload new picture
# URL should be: https://domain:8443/media/profile_pictures/xxx.png
```

---

## 🔍 Troubleshooting

### If SSL Certificate Errors After Restore

1. **Check certificate path in nginx config**:
   ```bash
   sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
     "grep ssl_certificate /opt/labcontrol/nginx/conf.d/labcontrol.conf"
   ```
   Should show `/etc/letsencrypt/live/...` (NOT `./nginx/ssl/`)

2. **Verify certificates exist**:
   ```bash
   sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
     "sudo ls -la /etc/letsencrypt/live/labmolecuar-portal-clientes-staging.com/"
   ```

3. **Renew if needed**:
   ```bash
   sshpass -p '39872327Seba.' ssh deploy@72.60.137.226
   docker stop root-traefik-1
   sudo certbot renew --force-renewal
   docker start root-traefik-1
   cd /opt/labcontrol
   docker compose -f docker-compose.prod.yml restart nginx
   ```

### If Port Lost in URLs

1. **Verify nginx uses $http_host**:
   ```bash
   sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
     "grep 'proxy_set_header Host' /opt/labcontrol/nginx/conf.d/labcontrol.conf"
   ```
   Should show `$http_host` (NOT `$host`)

2. **Restart nginx after config change**:
   ```bash
   sshpass -p '39872327Seba.' ssh deploy@72.60.137.226 \
     "cd /opt/labcontrol && docker compose -f docker-compose.prod.yml restart nginx"
   ```

---

## 📝 Notes

- **DO NOT commit `.env.production.backup` to git** - it contains secrets
- This backup is stored locally in the repository under `backups/`
- For disaster recovery, keep an offsite copy of this backup
- Certificate auto-renewal is configured - certificates should renew automatically every 90 days

---

## 🔗 Related Documentation

- Full deployment guide: [DEPLOYMENT.md](../../DEPLOYMENT.md)
- Recent fixes: See "Recent Updates & Fixes" section in DEPLOYMENT.md
- Git commits:
  - SSL fix: `5e9091a` - Use Let's Encrypt certificates directly
  - Django admin fix: `9a4a283` - Preserve port in Django admin redirects
  - Profile pictures fix: `e78c0e0` - Use $http_host for all proxy locations

---

**Backup Created By**: Claude Code
**Backup Date**: March 22, 2026
**Verified Working**: ✅ Yes
