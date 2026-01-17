# Dependency Vulnerability Scanning

**Last Updated:** 2025-12-26
**Status:** Active - Integrated into CI/CD pipeline

---

## Overview

LabControl uses **pip-audit** to continuously scan Python dependencies for known security vulnerabilities. This automated process helps identify and fix security issues in third-party packages before they can be exploited.

### Why pip-audit?

- **Actively maintained** by the Python Packaging Authority (PyPA)
- **Uses OSV database** (Open Source Vulnerabilities) for comprehensive coverage
- **Fast and accurate** vulnerability detection
- **Simple integration** with CI/CD pipelines
- **Detailed CVE information** for each vulnerability

---

## Quick Start

### Run Vulnerability Scan Locally

```bash
# Inside Docker container
docker-compose exec web pip-audit

# With detailed descriptions
docker-compose exec web pip-audit --desc

# Check specific requirements file
docker-compose exec web pip-audit -r requirements/base.txt
```

### Expected Output

**No vulnerabilities:**
```
No known vulnerabilities found
```

**Vulnerabilities found:**
```
Found 2 known vulnerabilities in 1 package
Name     Version ID             Fix Versions
-------- ------- -------------- ------------
requests 2.31.0  CVE-2024-35195 2.32.0,2.32.1
requests 2.31.0  CVE-2024-47081 2.32.4
```

---

## How to Fix Vulnerabilities

### Step 1: Run the Scan

```bash
docker-compose exec web pip-audit --desc
```

### Step 2: Review the Results

For each vulnerability, note:
- **Package name** - Which dependency is affected
- **Current version** - The vulnerable version you're using
- **CVE ID** - Common Vulnerabilities and Exposures identifier
- **Fix versions** - Versions that patch the vulnerability

### Step 3: Update Requirements Files

Update the affected package in the appropriate requirements file:

**For production dependencies:**
```bash
# Edit requirements/base.txt
requests==2.32.4  # Updated from 2.31.0 to fix CVE-2024-35195, CVE-2024-47081
```

**For development dependencies:**
```bash
# Edit requirements/dev.txt
werkzeug==3.1.4  # Updated from 3.0.2 to fix CVE-2024-34069
```

**Best practices:**
- Always add a comment explaining which CVEs the update fixes
- Use exact version pinning (`==`) not ranges (`>=`)
- Update to the latest stable patch version when possible

### Step 4: Rebuild and Test

```bash
# Rebuild Docker containers with updated dependencies
docker-compose down
docker-compose build web
docker-compose up -d

# Verify vulnerabilities are fixed
docker-compose exec web pip-audit

# Run test suite to ensure no breaking changes
docker-compose exec web pytest
```

### Step 5: Commit the Changes

```bash
git add requirements/
git commit -m "security: fix CVE-XXXX-XXXXX in package-name"
git push
```

---

## CI/CD Integration

### GitHub Actions Workflow

pip-audit runs automatically in the **security** job on every:
- Push to `main` or `develop` branches
- Pull request targeting `main` or `develop`

**Workflow file:** `.github/workflows/ci.yml`

```yaml
security:
  name: Security Checks
  runs-on: ubuntu-latest

  steps:
    - name: Install base dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements/base.txt

    - name: Install security tools
      run: pip install pip-audit bandit

    - name: Run pip-audit (dependency vulnerability scan)
      run: pip-audit --desc
```

**If the scan fails:**
1. Check the GitHub Actions logs
2. Review the vulnerabilities listed
3. Update the affected packages
4. Push the fix and re-run the workflow

---

## Common Scenarios

### Scenario 1: Major Version Update Required

**Problem:** The fix requires upgrading to a new major version (e.g., Django 3.x → 4.x)

**Solution:**
1. Review the package's changelog for breaking changes
2. Update the package version
3. Run the full test suite
4. Fix any test failures or deprecation warnings
5. Update documentation if APIs changed

### Scenario 2: No Fix Available Yet

**Problem:** pip-audit finds a vulnerability but no patched version exists

**Solution:**
1. Check the CVE severity (CVSS score)
2. If critical: Consider temporary mitigation (firewall rules, input validation)
3. Monitor the package's GitHub for updates
4. Consider switching to an alternative package if security is critical
5. Document the issue in `SECURITY.md`

### Scenario 3: False Positive

**Problem:** pip-audit reports a vulnerability that doesn't apply to your usage

**Solution:**
1. Verify it's truly a false positive (read the CVE details)
2. Document why it doesn't apply in comments
3. Consider ignoring specific vulnerabilities (use with caution):
   ```bash
   pip-audit --ignore-vuln CVE-XXXX-XXXXX
   ```

---

## Vulnerability Audit History

### 2025-12-26: Initial Security Audit

**Scanned:** All production and development dependencies
**Found:** 35 known vulnerabilities in 7 packages
**Fixed:** All 35 vulnerabilities

| Package | Old Version | New Version | CVEs Fixed |
|---------|-------------|-------------|------------|
| Django | 4.2.11 | 4.2.27 | 23 PYSEC/CVE vulnerabilities |
| django-allauth | 0.63.2 | 65.13.0 | CVE-2025-65431, CVE-2025-65430 |
| djangorestframework | 3.15.1 | 3.15.2 | CVE-2024-21520 |
| djangorestframework-simplejwt | 5.3.1 | 5.5.1 | CVE-2024-22513 |
| requests | 2.31.0 | 2.32.4 | CVE-2024-35195, CVE-2024-47081 |
| urllib3 | 2.5.0 | 2.6.0 | CVE-2025-66418, CVE-2025-66471 |
| werkzeug | 3.0.2 | 3.1.4 | CVE-2024-34069, CVE-2024-49766, CVE-2024-49767, CVE-2025-66221 |

**Test Results:** All 211 tests passing after upgrades
**Status:** ✅ No known vulnerabilities

---

## Best Practices

### Development Workflow

1. **Run scans regularly** (at least weekly)
   ```bash
   docker-compose exec web pip-audit
   ```

2. **Before major releases** (always scan)
   ```bash
   docker-compose exec web pip-audit --desc > security-audit.txt
   ```

3. **Subscribe to security advisories**
   - GitHub Security Advisories for your dependencies
   - Django Security Mailing List
   - Python Security Response Team

### Dependency Management

1. **Pin exact versions** in requirements files
   ```python
   # Good
   Django==4.2.27

   # Bad (unpredictable)
   Django>=4.2.0
   ```

2. **Separate requirements files**
   - `requirements/base.txt` - Production dependencies
   - `requirements/dev.txt` - Development tools
   - `requirements/prod.txt` - Production-specific (if needed)

3. **Document security updates**
   ```python
   # requirements/base.txt
   Django==4.2.27  # Updated from 4.2.11 to fix 23 security vulnerabilities
   ```

4. **Test thoroughly after updates**
   - Run full test suite
   - Check for deprecation warnings
   - Test critical user flows manually

---

## Troubleshooting

### pip-audit not found

```bash
# Install pip-audit
docker-compose exec web pip install pip-audit

# Or rebuild container
docker-compose build web
```

### Scan takes too long

```bash
# Use local cache
docker-compose exec web pip-audit --cache-dir /tmp/pip-audit-cache

# Or scan specific file
docker-compose exec web pip-audit -r requirements/base.txt
```

### Different results locally vs CI

```bash
# Ensure same Python version
python --version  # Should match CI (3.11)

# Ensure same dependencies
pip freeze | grep -i package-name

# Clear cache and reinstall
pip cache purge
pip install -r requirements/base.txt --force-reinstall
```

---

## Additional Resources

- **pip-audit documentation:** https://github.com/pypa/pip-audit
- **OSV database:** https://osv.dev/
- **CVE database:** https://cve.mitre.org/
- **Django security:** https://docs.djangoproject.com/en/stable/internals/security/
- **OWASP Top 10:** https://owasp.org/www-project-top-ten/

---

## Next Steps

1. **Set up automated alerts** - Configure GitHub to notify on new vulnerabilities
2. **Dependency updates schedule** - Review and update dependencies monthly
3. **Security policy** - Create `SECURITY.md` with vulnerability reporting process
4. **Penetration testing** - Schedule regular security audits
5. **Dependency graph** - Monitor dependency tree for indirect vulnerabilities

---

**Questions or issues?** Check the GitHub Actions logs or contact the security team.
