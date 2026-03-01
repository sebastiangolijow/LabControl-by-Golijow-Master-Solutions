# SSL Certificates Directory

This directory will contain your SSL/TLS certificates.

## Production Setup (Let's Encrypt)

After deploying to VPS, generate certificates with:

```bash
sudo certbot certonly --standalone \
    -d lab.yourdomain.com \
    -d www.lab.yourdomain.com \
    --email your-email@example.com \
    --agree-tos

# Copy to nginx directory
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/fullchain.pem /opt/labcontrol/nginx/ssl/
sudo cp /etc/letsencrypt/live/lab.yourdomain.com/privkey.pem /opt/labcontrol/nginx/ssl/
sudo chown deploy:deploy /opt/labcontrol/nginx/ssl/*.pem
```

## Local Development (Self-Signed Certificate)

For testing locally:

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/ssl/privkey.pem \
    -out nginx/ssl/fullchain.pem \
    -subj "/C=AR/ST=BuenosAires/L=BuenosAires/O=LabControl/CN=localhost"
```

**Note**: Self-signed certificates will show browser warnings. Use only for testing.

## Certificate Renewal

Certificates auto-renew via cron job (see DEPLOYMENT_PLAN.md):

```bash
0 0 * * * certbot renew --quiet --deploy-hook "cp /etc/letsencrypt/live/lab.yourdomain.com/*.pem /opt/labcontrol/nginx/ssl/ && docker restart labcontrol_nginx"
```

## Files Required

- `fullchain.pem` - Full certificate chain
- `privkey.pem` - Private key

**Security**: Never commit private keys to version control!
