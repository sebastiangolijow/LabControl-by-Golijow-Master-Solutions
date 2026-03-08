# LabControl Deployment Checklist

**VPS Details:**
- **Hostname**: srv879400.hstgr.cloud
- **IP Address**: 72.60.137.226
- **Provider**: Hostinger KVM 2
- **Status**: Active until 2026-03-18

---

## ☑️ Pre-Deployment

- [ ] **Domain configured** (optional but recommended)
  - If using domain: Point DNS A record to `72.60.137.226`
  - If no domain: Will use IP address directly
  - DNS propagation: Wait 15 min - 2 hours after configuring

- [ ] **SSH access verified**
  ```bash
  ssh root@72.60.137.226
  ```

- [ ] **OS confirmed** (should be Ubuntu 22.04 LTS)
  ```bash
  lsb_release -a
  ```

---

## 🔐 Step 1: Initial VPS Setup (30 minutes)

### 1.1 System Update
```bash
ssh root@72.60.137.226
apt update && apt upgrade -y
timedatectl set-timezone America/Argentina/Buenos_Aires  # Adjust to your timezone
```

### 1.2 Create Deploy User
```bash
adduser deploy
usermod -aG sudo deploy

# Setup SSH key for deploy user
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### 1.3 SSH Hardening
```bash
nano /etc/ssh/sshd_config

# Make these changes:
# PermitRootLogin no
# PasswordAuthentication no

systemctl restart sshd

# IMPORTANT: Test SSH with deploy user before logging out!
# Open new terminal and test:
ssh deploy@72.60.137.226
```

### 1.4 Firewall Setup
```bash
# Switch to deploy user
su - deploy

# Configure UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Verify
sudo ufw status verbose
```

### 1.5 Install fail2ban
```bash
sudo apt install fail2ban -y

sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 22
logpath = /var/log/auth.log

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
EOF

sudo systemctl enable fail2ban
sudo systemctl start fail2ban
sudo fail2ban-client status
```

---

## 🐳 Step 2: Install Docker & Nginx (20 minutes)

### 2.1 Install Docker
```bash
# Remove old versions
sudo apt remove docker docker-engine docker.io containerd runc

# Install prerequisites
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Setup repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add deploy to docker group
sudo usermod -aG docker deploy

# Log out and back in for group changes
exit
ssh deploy@72.60.137.226

# Verify
docker --version
docker compose version

# Enable Docker on boot
sudo systemctl enable docker
```

### 2.2 Install Nginx
```bash
sudo apt install nginx -y
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```

---

## 📦 Step 3: Deploy Application (30 minutes)

### 3.1 Create Application Directory
```bash
sudo mkdir -p /opt/labcontrol
sudo chown deploy:deploy /opt/labcontrol
cd /opt/labcontrol
```

### 3.2 Upload/Clone Application Code

**Option A: Upload from local machine (recommended for now)**
```bash
# Run this from your LOCAL machine (macOS):
cd /Users/cevichesmac/Desktop

# Upload backend
rsync -avz --exclude '__pycache__' --exclude '*.pyc' --exclude 'media' \
  labcontrol/ deploy@72.60.137.226:/opt/labcontrol/

# Upload frontend build (after building locally)
cd labcontrol-frontend
npm run build
rsync -avz dist/ deploy@72.60.137.226:/opt/labcontrol/frontend/dist/
```

**Option B: Clone from Git (if repository is ready)**
```bash
# On VPS:
cd /opt/labcontrol
git clone https://github.com/yourusername/labcontrol.git .
```

### 3.3 Create Environment File
```bash
cd /opt/labcontrol
cp .env.production.template .env.production
nano .env.production

# Fill in these critical values:
# DJANGO_SECRET_KEY - Generate with: openssl rand -base64 64
# DJANGO_ALLOWED_HOSTS - Add: 72.60.137.226 (or your domain)
# POSTGRES_PASSWORD - Generate with: openssl rand -base64 32
# EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
# Update all "CHANGE-THIS" placeholders
```

### 3.4 Update Nginx Configuration
```bash
nano /opt/labcontrol/nginx/conf.d/labcontrol.conf

# Change server_name from:
# server_name lab.yourdomain.com www.lab.yourdomain.com;

# To (if using IP):
# server_name 72.60.137.226;

# Or (if using domain):
# server_name lab.yourdomain.com;
```

---

## 🚀 Step 4: Build and Start (20 minutes)

### 4.1 Build Docker Images
```bash
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml build
```

### 4.2 Start Database First
```bash
docker compose -f docker-compose.prod.yml up -d db redis
sleep 10  # Wait for DB to be ready
```

### 4.3 Run Migrations
```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
```

### 4.4 Create Superuser
```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
```

### 4.5 Create Seed Users (Optional)
```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py create_seed_users
```

### 4.6 Collect Static Files
```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
```

### 4.7 Start All Services
```bash
docker compose -f docker-compose.prod.yml up -d
```

### 4.8 Check Logs
```bash
docker compose -f docker-compose.prod.yml logs -f

# Press Ctrl+C to exit
```

### 4.9 Verify Services
```bash
docker compose -f docker-compose.prod.yml ps

# All containers should show "Up" status
```

---

## 🔒 Step 5: SSL Certificate (15 minutes)

### Option A: Using Domain (Let's Encrypt - Free)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Stop Nginx container
docker compose -f /opt/labcontrol/docker-compose.prod.yml stop nginx

# Generate certificate
sudo certbot certonly --standalone \
    -d lab.yourdomain.com \
    --email your-email@example.com \
    --agree-tos \
    --non-interactive

# Copy certificates
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/fullchain.pem /opt/labcontrol/nginx/ssl/
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/privkey.pem /opt/labcontrol/nginx/ssl/
sudo chown deploy:deploy /opt/labcontrol/nginx/ssl/*.pem

# Start Nginx
docker compose -f /opt/labcontrol/docker-compose.prod.yml up -d nginx

# Setup auto-renewal
(sudo crontab -l 2>/dev/null; echo "0 0 * * * certbot renew --quiet --deploy-hook 'cp /etc/letsencrypt/live/lab.yourdomain.com/*.pem /opt/labcontrol/nginx/ssl/ && docker restart labcontrol_nginx'") | sudo crontab -
```

### Option B: Self-Signed (Testing Only)
```bash
cd /opt/labcontrol/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout privkey.pem \
    -out fullchain.pem \
    -subj "/C=AR/ST=BuenosAires/L=BuenosAires/O=LabControl/CN=72.60.137.226"

docker compose -f /opt/labcontrol/docker-compose.prod.yml restart nginx
```

---

## 💾 Step 6: Setup Backups (10 minutes)

### 6.1 Test Backup Script
```bash
cd /opt/labcontrol
source .env.production
sudo -E ./scripts/backup.sh

# Verify backup was created
ls -lh backups/postgres/
ls -lh backups/media/
```

### 6.2 Schedule Daily Backups
```bash
crontab -e

# Add this line (runs daily at 2 AM):
0 2 * * * /bin/bash -c 'source /opt/labcontrol/.env.production && /opt/labcontrol/scripts/backup.sh' >> /opt/labcontrol/backups/logs/cron.log 2>&1
```

### 6.3 Setup Health Checks
```bash
# Update health check script
nano /opt/labcontrol/scripts/health_check.sh
# Change DOMAIN to your actual domain or http://72.60.137.226

crontab -e

# Add this line (runs every 5 minutes):
*/5 * * * * DOMAIN=http://72.60.137.226 /opt/labcontrol/scripts/health_check.sh >> /opt/labcontrol/logs/health.log 2>&1
```

---

## ✅ Step 7: Verification & Testing

### 7.1 Check Service Health
```bash
cd /opt/labcontrol
./scripts/deploy.sh health
```

### 7.2 Access Application
```bash
# Open in browser:
http://72.60.137.226  # or https://lab.yourdomain.com
```

### 7.3 Test Authentication
- [ ] Login with superuser credentials
- [ ] Register new patient user
- [ ] Test password reset email
- [ ] Verify JWT token refresh

### 7.4 Test Core Features
- [ ] Create a study
- [ ] Upload study result PDF
- [ ] Download study result
- [ ] View study list
- [ ] Test user search (doctors/patients)

### 7.5 Test Admin Panel
```bash
# Access Django admin:
http://72.60.137.226/admin/  # or https://lab.yourdomain.com/admin/
```

---

## 📊 Post-Deployment Monitoring (First 24 hours)

### Check Logs Regularly
```bash
# All services
docker compose -f /opt/labcontrol/docker-compose.prod.yml logs -f

# Specific service
docker compose -f /opt/labcontrol/docker-compose.prod.yml logs -f web
docker compose -f /opt/labcontrol/docker-compose.prod.yml logs -f celery_worker

# Nginx access logs
tail -f /opt/labcontrol/nginx/logs/labcontrol_access.log

# Health check logs
tail -f /opt/labcontrol/logs/health.log
```

### Monitor Resources
```bash
# Docker stats
docker stats

# System resources
htop  # or: top
df -h  # disk usage
```

### Check Fail2ban
```bash
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

---

## 🔧 Common Commands Reference

```bash
cd /opt/labcontrol

# View status
./scripts/deploy.sh status

# View logs
./scripts/deploy.sh logs

# Restart services
./scripts/deploy.sh restart

# Run backup manually
./scripts/deploy.sh backup

# Check health
./scripts/deploy.sh health

# Update application
./scripts/deploy.sh update

# Django shell
./scripts/deploy.sh shell

# Database shell
./scripts/deploy.sh dbshell
```

---

## 🚨 Emergency Procedures

### Rollback Database
```bash
cd /opt/labcontrol
ls -lh backups/postgres/  # Find backup file
./scripts/restore.sh backups/postgres/db_YYYYMMDD_HHMMSS.sql.gz
```

### Restart All Services
```bash
cd /opt/labcontrol
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

### Check What's Wrong
```bash
# Services status
docker compose -f /opt/labcontrol/docker-compose.prod.yml ps

# Recent errors
docker compose -f /opt/labcontrol/docker-compose.prod.yml logs --tail=100

# Disk space
df -h

# Memory usage
free -h
```

---

## ✅ Final Checklist

- [ ] VPS hardened (firewall, fail2ban, SSH)
- [ ] Docker and Nginx installed
- [ ] Application deployed and running
- [ ] Database migrated and superuser created
- [ ] SSL certificate installed (Let's Encrypt or self-signed)
- [ ] Automated backups scheduled (cron)
- [ ] Health checks running
- [ ] Application tested end-to-end
- [ ] Admin panel accessible
- [ ] Email notifications working
- [ ] Documentation saved in password manager:
  - VPS IP: 72.60.137.226
  - SSH key location
  - Database password
  - Django SECRET_KEY
  - Superuser credentials
  - Email SMTP credentials

---

**Estimated Total Time**: 2-3 hours

**Next Maintenance**: Weekly (see DEPLOYMENT_README.md)

---

*Created: 2026-02-22*
*VPS: srv879400.hstgr.cloud (72.60.137.226)*
