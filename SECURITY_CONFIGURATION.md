# Security Configuration Guide

**Last Updated:** 2025-12-26
**Status:** Production-Ready Security Configuration

---

## Overview

LabControl implements multiple layers of security following OWASP best practices. This guide documents all security features, their configuration, and how to maintain them.

### Security Features Implemented

1. ✅ **Email Verification** - Prevents fake account registration
2. ✅ **Login Rate Limiting** - Prevents brute-force attacks
3. ✅ **Dependency Vulnerability Scanning** - Automated security updates
4. ✅ **Custom Admin URL** - Obscures admin panel from attackers
5. ✅ **Content Security Policy (CSP)** - Prevents XSS and injection attacks

---

## 1. Email Verification

### Purpose
Ensures that only users with valid email addresses can access the platform, preventing spam accounts and fake registrations.

### Implementation
**Location:** `config/settings/base.py`

```python
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
```

### How It Works
1. User registers with email and password
2. System sends verification email with unique token
3. User must click verification link to activate account
4. Only verified users can log in

### Testing
```bash
# Create test user
docker-compose exec web python manage.py shell
>>> from apps.users.models import User
>>> user = User.objects.create_user(email='test@example.com', password='TestPass123!')
>>> user.is_verified
False

# Verify manually
>>> user.is_verified = True
>>> user.save()
```

### Configuration
**Environment Variables (.env):**
```bash
# Email backend for verification emails
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@labcontrol.com
```

**Production Checklist:**
- [ ] Set up SMTP credentials (Gmail, SendGrid, or AWS SES)
- [ ] Test verification email delivery
- [ ] Configure email templates branding
- [ ] Set up email rate limiting (if needed)

---

## 2. Login Rate Limiting

### Purpose
Prevents brute-force password attacks by limiting login attempts per IP address.

### Implementation
**Location:** `apps/users/throttles.py`

```python
class LoginRateThrottle(SimpleRateThrottle):
    """
    Rate: 5 attempts per 15 minutes per IP address.
    """
    scope = "login"
    rate = "5/15m"
```

### How It Works
1. System tracks login attempts by IP address
2. After 5 failed attempts, IP is blocked for 15 minutes
3. Returns HTTP 429 (Too Many Requests) for blocked IPs
4. Counter resets after 15 minutes

### Rate Limits
| Endpoint | Rate Limit | Scope |
|----------|------------|-------|
| Login | 5 per 15 minutes | Per IP |
| Password Reset | 3 per hour | Per IP |
| Registration | 5 per hour | Per IP |
| API (Anonymous) | 100 per hour | Per IP |
| API (Authenticated) | 1000 per hour | Per User |

### Testing
```bash
# Run rate limiting tests
docker-compose exec web pytest tests/test_rate_limiting.py -v
```

### Configuration
**Location:** `config/settings/base.py`

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "password_reset": "3/hour",
        "registration": "5/hour",
    },
}
```

**Customization:**
To adjust rate limits, edit the rates in `base.py` or override in custom throttle classes.

**Bypass for Testing:**
```python
# In test settings (config/settings/test.py)
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []  # Disables throttling in tests
```

---

## 3. Dependency Vulnerability Scanning

### Purpose
Automatically identifies and alerts on known security vulnerabilities in Python dependencies.

### Implementation
**Tool:** pip-audit (integrated into CI/CD)

**Location:** `.github/workflows/ci.yml`

```yaml
- name: Run pip-audit (dependency vulnerability scan)
  run: pip-audit --desc
```

### How It Works
1. pip-audit scans all installed packages
2. Queries OSV (Open Source Vulnerabilities) database
3. Reports any known CVEs in dependencies
4. Fails CI/CD pipeline if critical vulnerabilities found

### Manual Scanning
```bash
# Scan all dependencies
docker-compose exec web pip-audit

# Scan specific requirements file
docker-compose exec web pip-audit -r requirements/base.txt

# With detailed descriptions
docker-compose exec web pip-audit --desc
```

### Vulnerability Fix Process
See `DEPENDENCY_SCANNING.md` for detailed instructions on:
- Running scans
- Interpreting results
- Updating vulnerable packages
- Testing after updates

### Recent Audit (2025-12-26)
✅ **All vulnerabilities fixed**
- Django: 4.2.11 → 4.2.27 (23 CVEs fixed)
- django-allauth: 0.63.2 → 65.13.0 (2 CVEs fixed)
- djangorestframework: 3.15.1 → 3.15.2 (1 CVE fixed)
- And 4 more packages updated

**Maintenance Schedule:**
- Run pip-audit: **Weekly** (automated in CI/CD)
- Review and update dependencies: **Monthly**
- Security patches: **Immediately** when critical CVEs found

---

## 4. Custom Admin URL

### Purpose
Obscures the Django admin panel URL to prevent automated attacks targeting `/admin/`.

### Implementation
**Location:** `config/urls.py`

```python
import os

# Security: Custom admin URL from environment variable
ADMIN_URL = os.getenv("ADMIN_URL", "admin/")

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    # ... other URLs
]
```

### Configuration
**Environment Variable (.env):**
```bash
# Development (default)
ADMIN_URL=admin/

# Production (example - choose your own!)
ADMIN_URL=secret-control-panel-xyz789/
```

**⚠️ IMPORTANT SECURITY NOTES:**
1. **Change in production** - Never use `admin/` in production
2. **Use unpredictable URL** - Combine random words and numbers
3. **Keep it secret** - Don't commit production URL to git
4. **Document securely** - Store production URL in password manager

### Best Practices

**Good Admin URLs:**
```
secret-lab-control-9876/
management-portal-abc123/
internal-dashboard-xyz456/
```

**Bad Admin URLs:**
```
admin123/               # Too predictable
administrator/          # Common guess
backend/                # Obvious
control-panel/          # Too generic
```

### Access Admin Panel

**Development:**
```
http://localhost:8000/admin/
```

**Production:**
```
https://yourdomain.com/your-secret-admin-url/
```

**Testing Custom URL:**
```bash
# Set custom URL
export ADMIN_URL="my-secret-panel/"

# Restart application
docker-compose restart web

# Access admin
curl http://localhost:8000/my-secret-panel/
```

---

## 5. Content Security Policy (CSP)

### Purpose
Prevents Cross-Site Scripting (XSS), clickjacking, and other code injection attacks by controlling what resources the browser can load.

### Implementation
**Package:** django-csp==4.0

**Location:** `config/settings/base.py`

```python
MIDDLEWARE = [
    # ... other middleware
    "csp.middleware.CSPMiddleware",  # Content Security Policy
    # ... more middleware
]

# CSP Configuration
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")  # unsafe-inline for Django admin
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'", "data:")
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_SRC = ("'none'",)
CSP_OBJECT_SRC = ("'none'",)
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_UPGRADE_INSECURE_REQUESTS = False  # True in production
CSP_INCLUDE_NONCE_IN = ["script-src"]
```

### Production Overrides
**Location:** `config/settings/prod.py`

```python
# Upgrade HTTP to HTTPS in production
CSP_UPGRADE_INSECURE_REQUESTS = True

# Optional: Report CSP violations
CSP_REPORT_URI = env("CSP_REPORT_URI", default=None)
```

### CSP Directives Explained

| Directive | Value | Purpose |
|-----------|-------|---------|
| `default-src` | `'self'` | Default policy for all resources |
| `script-src` | `'self'` | Only allow scripts from same origin |
| `style-src` | `'self'` `'unsafe-inline'` | Allow inline styles for Django admin |
| `img-src` | `'self'` `data:` `https:` | Allow images from same origin, data URIs, and HTTPS |
| `font-src` | `'self'` `data:` | Allow fonts from same origin and data URIs |
| `connect-src` | `'self'` | Allow AJAX/WebSocket to same origin only |
| `frame-src` | `'none'` | Block all iframes |
| `object-src` | `'none'` | Block plugins (Flash, etc.) |
| `base-uri` | `'self'` | Prevent base tag hijacking |
| `form-action` | `'self'` | Forms can only submit to same origin |
| `frame-ancestors` | `'none'` | Prevent clickjacking (same as X-Frame-Options: DENY) |

### Customizing CSP

**Allow external API:**
```python
CSP_CONNECT_SRC = ("'self'", "https://api.external-service.com")
```

**Allow Google Fonts:**
```python
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_STYLE_SRC = ("'self'", "https://fonts.googleapis.com", "'unsafe-inline'")
```

**Allow CDN for static files:**
```python
CSP_SCRIPT_SRC = ("'self'", "https://cdn.yourcompany.com")
CSP_STYLE_SRC = ("'self'", "https://cdn.yourcompany.com")
```

### Testing CSP

**Check CSP Header:**
```bash
# Test with curl
curl -I https://yourdomain.com/

# Expected header:
# Content-Security-Policy: default-src 'self'; script-src 'self'; ...
```

**Browser Console:**
Open browser DevTools → Console. CSP violations will appear as errors:
```
Refused to load the script 'https://evil.com/malicious.js' because it violates
the following Content Security Policy directive: "script-src 'self'".
```

**Online Testing Tools:**
- [CSP Evaluator](https://csp-evaluator.withgoogle.com/)
- [Security Headers](https://securityheaders.com/)

### CSP Violation Reporting

**Set up reporting endpoint:**
```bash
# .env
CSP_REPORT_URI=https://yourdomain.com/csp-violation-report/
```

**Implement violation handler:**
```python
# apps/core/views.py
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import json
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
def csp_violation_report(request):
    if request.method == 'POST':
        try:
            violation = json.loads(request.body)
            logger.warning(f"CSP Violation: {violation}")
        except Exception as e:
            logger.error(f"Error parsing CSP report: {e}")
    return HttpResponse(status=204)
```

---

## Additional Security Headers

### Automatically Applied by Django

**X-Content-Type-Options:**
```python
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevents MIME-sniffing
```

**X-Frame-Options:**
```python
X_FRAME_OPTIONS = "DENY"  # Prevents clickjacking
```

**X-XSS-Protection:**
```python
SECURE_BROWSER_XSS_FILTER = True  # Legacy XSS protection
```

### Production-Only Security Headers
**Location:** `config/settings/prod.py`

```python
# Force HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie security
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
```

---

## Security Testing Checklist

### Before Production Deployment

- [ ] Email verification working
- [ ] Rate limiting tested (see `tests/test_rate_limiting.py`)
- [ ] pip-audit shows no vulnerabilities
- [ ] Custom admin URL configured (not `admin/`)
- [ ] CSP headers present in responses
- [ ] All security headers validated (use securityheaders.com)
- [ ] HTTPS enforced
- [ ] Environment variables secured (not in git)
- [ ] Database passwords strong and unique
- [ ] SECRET_KEY is random 50+ character string
- [ ] DEBUG = False in production
- [ ] ALLOWED_HOSTS configured correctly
- [ ] Sensitive data encrypted at rest
- [ ] Backups configured and tested
- [ ] Security monitoring enabled (Sentry)

### Automated Security Tests

```bash
# Run all security-related tests
docker-compose exec web pytest tests/test_rate_limiting.py tests/test_email_verification.py -v

# Run vulnerability scan
docker-compose exec web pip-audit

# Check for outdated packages
docker-compose exec web pip list --outdated

# Run security linters
docker-compose exec web bandit -r apps/ config/
```

---

## Security Monitoring

### Logging
All security events are logged:
- Failed login attempts
- Rate limit violations
- Email verification attempts
- Admin panel access

**Location:** `config/settings/base.py` → `LOGGING`

### Sentry Integration (Production)
**Environment Variable:**
```bash
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

**Auto-reports:**
- Unhandled exceptions
- Security violations
- Performance issues
- Error stack traces

---

## Security Incident Response

### If You Suspect a Breach

1. **Immediate Actions:**
   - Rotate all secrets (SECRET_KEY, database passwords, API keys)
   - Force logout all users (invalidate sessions)
   - Review access logs for suspicious activity
   - Enable maintenance mode if necessary

2. **Investigation:**
   - Check Sentry for unusual errors
   - Review Django admin access logs
   - Audit recent database changes (simple-history)
   - Check for unauthorized user accounts

3. **Remediation:**
   - Patch vulnerabilities
   - Update dependencies
   - Review and strengthen security policies
   - Notify affected users (if PII compromised)

4. **Prevention:**
   - Run full security audit
   - Enhance monitoring
   - Update incident response plan

### Emergency Commands

```bash
# Rotate Django secret key
python manage.py shell
>>> from django.core.management.utils import get_random_secret_key
>>> print(get_random_secret_key())

# Clear all sessions (logs out all users)
docker-compose exec web python manage.py clearsessions

# Review recent admin actions
docker-compose exec web python manage.py shell
>>> from django.contrib.admin.models import LogEntry
>>> LogEntry.objects.all().order_by('-action_time')[:20]
```

---

## Compliance & Standards

### OWASP Top 10 Coverage

1. ✅ **A01: Broken Access Control** - Role-based permissions, multi-tenant isolation
2. ✅ **A02: Cryptographic Failures** - HTTPS, secure cookies, password hashing
3. ✅ **A03: Injection** - Django ORM (prevents SQL injection), CSP (prevents XSS)
4. ✅ **A04: Insecure Design** - Security-first architecture
5. ✅ **A05: Security Misconfiguration** - This guide ensures proper configuration
6. ✅ **A06: Vulnerable Components** - pip-audit automated scanning
7. ✅ **A07: Authentication Failures** - Email verification, rate limiting, strong passwords
8. ✅ **A08: Software and Data Integrity** - Signed commits, dependency pinning
9. ✅ **A09: Logging Failures** - Comprehensive logging, Sentry monitoring
10. ✅ **A10: SSRF** - Validated URLs, limited external requests

### HIPAA Considerations (Medical Data)

While LabControl is not HIPAA-certified out-of-the-box, it implements many required controls:
- ✅ Audit trails (django-simple-history)
- ✅ Access controls (RBAC)
- ✅ Encryption in transit (HTTPS)
- ✅ Session timeouts
- ✅ Unique user identification
- ⚠️ **Still needed:** Encryption at rest, BAA agreements, physical security

**For full HIPAA compliance, consult a compliance specialist.**

---

## Maintenance Schedule

### Daily
- Monitor Sentry for security alerts
- Review failed login attempts

### Weekly
- Run pip-audit vulnerability scan
- Review access logs

### Monthly
- Update dependencies (patch versions)
- Security audit of new code
- Review and rotate API keys

### Quarterly
- Full penetration testing
- Review and update security policies
- Security training for team
- Disaster recovery drill

### Annually
- Major dependency updates
- Third-party security audit
- Review compliance requirements
- Update incident response plan

---

## Resources

### Internal Documentation
- `DEPENDENCY_SCANNING.md` - Vulnerability scanning guide
- `MVP.md` - Feature implementation details
- `PATIENT_WORKFLOW.md` - Security in patient workflows

### External Resources
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Django Security Guide](https://docs.djangoproject.com/en/stable/topics/security/)
- [CSP Documentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [django-csp Documentation](https://django-csp.readthedocs.io/)
- [pip-audit GitHub](https://github.com/pypa/pip-audit)

---

## Support

**Questions or security concerns?**
- Review this documentation first
- Check the test suite for examples
- Consult OWASP resources
- For critical security issues, contact security team directly (not via public channels)

---

**Last Updated:** 2025-12-26
**Next Review:** 2026-01-26
