# LabControl Configuration Backups Index

This directory contains verified working configuration backups for disaster recovery and rollback purposes.

---

## Available Backups

### 📦 2026-03-22-working-config (✅ VERIFIED)

**Status**: Active, fully tested and verified working
**Date**: March 22, 2026
**Git Commit**: `e78c0e0`

**What's Working**:
- ✅ SSL Certificate (Let's Encrypt, valid until June 20, 2026)
- ✅ Django Admin at `/django-admin/` with port `:8443` preserved
- ✅ Profile picture URLs include port `:8443`
- ✅ All API endpoints working
- ✅ Frontend loads without SSL warnings

**Contains**:
- `labcontrol.conf` - Nginx configuration
- `docker-compose.prod.yml` - Docker Compose setup
- `.env.production.backup` - Environment variables (with secrets, not in git)
- `README.md` - Detailed documentation and restore instructions
- `VERIFICATION.txt` - Test results proving configuration works
- `GIT_COMMIT.txt` - Git commit hash for reference
- `restore.sh` - Automated restore script

**Quick Restore**:
```bash
cd backups/2026-03-22-working-config
./restore.sh nginx    # Restore nginx only (quick)
./restore.sh env      # Restore environment variables
./restore.sh full     # Full restore (nuclear option)
```

**Use This Backup When**:
- SSL certificate issues after renewal
- Django admin redirect loses port
- Profile pictures URLs missing port
- After nginx configuration changes that break the site
- Need to rollback to a known-good state

---

## How to Create a New Backup

```bash
# 1. Create backup directory
BACKUP_DATE=$(date +%Y-%m-%d)
BACKUP_DIR="backups/${BACKUP_DATE}-description"
mkdir -p "$BACKUP_DIR"

# 2. Copy local configuration files
cp nginx/conf.d/labcontrol.conf "$BACKUP_DIR/"
cp docker-compose.prod.yml "$BACKUP_DIR/"

# 3. Backup server .env.production
sshpass -p '39872327Seba.' scp \
  deploy@72.60.137.226:/opt/labcontrol/.env.production \
  "$BACKUP_DIR/.env.production.backup"

# 4. Save git commit
git log -1 --format="%H %s" > "$BACKUP_DIR/GIT_COMMIT.txt"

# 5. Create README and VERIFICATION files
# Document what's working and how to restore

# 6. Commit to git (backup files will be in git, .env will be gitignored)
git add backups/
git commit -m "backup: create verified configuration backup for $BACKUP_DATE"
```

---

## Backup Strategy

### When to Create a Backup

Create a new backup whenever:
1. ✅ **After fixing a critical issue** - Like today's SSL and port preservation fixes
2. ✅ **Before major changes** - Before modifying nginx config, docker-compose, etc.
3. ✅ **After successful deployment** - When everything is verified working in production
4. ✅ **Before certificate renewal** - Before running `certbot renew`
5. ✅ **Monthly** - Create a monthly backup as a safety net

### What Gets Backed Up

**Included**:
- ✅ Nginx configuration (`labcontrol.conf`)
- ✅ Docker Compose file (`docker-compose.prod.yml`)
- ✅ Environment variables (`.env.production.backup` - gitignored)
- ✅ Git commit hash for code reference
- ✅ Documentation (README, VERIFICATION)
- ✅ Restore scripts

**NOT Included** (backed up separately):
- ❌ Database dumps (use separate database backup strategy)
- ❌ Media files (use separate media backup strategy)
- ❌ Docker images (can be rebuilt from Dockerfile)
- ❌ SSL certificates (managed by Let's Encrypt, auto-renewed)

### Retention Policy

- **Current working backup**: Keep indefinitely
- **Monthly backups**: Keep for 1 year
- **Pre-change backups**: Keep for 3 months
- **Deprecated backups**: Archive to external storage after 6 months

---

## Disaster Recovery Plan

### Scenario 1: Nginx Configuration Broken

**Symptoms**: Site not loading, SSL errors, port issues
**Recovery**:
```bash
cd backups/2026-03-22-working-config
./restore.sh nginx
```
**Downtime**: ~30 seconds

### Scenario 2: Environment Variables Corrupted

**Symptoms**: Django errors, database connection failures
**Recovery**:
```bash
cd backups/2026-03-22-working-config
./restore.sh env
```
**Downtime**: ~2-3 minutes

### Scenario 3: Complete System Failure

**Symptoms**: Everything broken, multiple services failing
**Recovery**:
```bash
cd backups/2026-03-22-working-config
./restore.sh full
```
**Downtime**: ~5-10 minutes

---

## Best Practices

1. **Test Backups**: Periodically test restore procedures in a non-production environment
2. **Document Changes**: Update README when configuration changes
3. **Version Control**: Keep backup files in git (except secrets)
4. **Offsite Copy**: Maintain a copy of critical backups outside the server
5. **Verification**: Always include VERIFICATION.txt with test results

---

**Last Updated**: March 22, 2026
**Maintained By**: Development Team
