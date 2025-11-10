# Security Policy
## 🔒 Security Best Practices

### API Key Management

**✅ DO:**
- Use environment variables or `.env` files for API keys
- Rotate keys regularly
- Use separate keys for development and production
- Store keys in secure secret management systems (AWS Secrets Manager, Azure Key Vault, etc.)

```python
# ✅ Good: Use environment variables
from apikeyrotator import APIKeyRotator
rotator = APIKeyRotator()  # Loads from .env or environment

# ✅ Good: Load from secure storage
import boto3
secrets = boto3.client('secretsmanager')
keys = secrets.get_secret_value(SecretId='api-keys')['SecretString']
rotator = APIKeyRotator(api_keys=keys.split(','))
```

**❌ DON'T:**
- Hardcode API keys in your source code
- Commit API keys to version control
- Share API keys in plain text
- Log API keys in application logs

```python
# ❌ Bad: Hardcoded keys
rotator = APIKeyRotator(api_keys=["hardcoded_key_123"])

# ❌ Bad: Keys in git
# .env file committed to repository
```

### Configuration Files

The library creates a `rotator_config.json` file to store learned configurations. This file:
- Does NOT contain API keys
- Only stores header patterns and domain configurations
- Is safe to commit to version control
- Should be reviewed before committing to ensure no sensitive data leaked

### Proxy Usage

If using proxies with authentication:

```python
# ✅ Use environment variables for proxy credentials
import os
proxy_user = os.getenv('PROXY_USER')
proxy_pass = os.getenv('PROXY_PASS')
proxy = f"http://{proxy_user}:{proxy_pass}@proxy.example.com:8080"

rotator = APIKeyRotator(
    api_keys=["key1"],
    proxy_list=[proxy]
)
```

### Logging

Be careful with logging levels in production:

```python
import logging

# ⚠️ DEBUG level may expose sensitive information
logging.basicConfig(level=logging.INFO)  # Use INFO in production

# ✅ Use custom logger with filtering
logger = logging.getLogger('apikeyrotator')
logger.setLevel(logging.WARNING)
```

## 🚨 Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### 1. **DO NOT** Open a Public Issue

Security vulnerabilities should not be disclosed publicly until they have been addressed.

### 2. Report Privately

**Email:** security@eclips-team.dev (preferred)  
**GitHub:** Use [GitHub Security Advisories](https://github.com/PrimeevolutionZ/apikeyrotator/security/advisories/new)

### 3. Provide Details

Include the following information:
- **Description**: Clear description of the vulnerability
- **Impact**: Potential impact and severity
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Affected Versions**: Which versions are affected
- **Proof of Concept**: Code or screenshots demonstrating the issue (if applicable)
- **Suggested Fix**: Any suggestions for fixing the issue (optional)

### Example Report Template

```
Subject: [SECURITY] Brief description of the vulnerability

Description:
[Detailed description of the vulnerability]

Impact:
[What can an attacker do with this vulnerability?]

Affected Versions:
[e.g., 0.4.0 - 0.4.1]

Steps to Reproduce:
1. [Step 1]
2. [Step 2]
3. [Step 3]

Proof of Concept:
[Code, screenshots, or other evidence]

Suggested Fix:
[Optional: Your suggestions for fixing the issue]
```

### 4. Response Timeline

- **Initial Response**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix Development**: Depends on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2 weeks
  - Low: 1 month
- **Public Disclosure**: After fix is released (coordinated disclosure)

## 🔐 Security Features

APIKeyRotator includes several security features:

### 1. Automatic Key Rotation
Invalid or compromised keys are automatically removed from the rotation pool:

```python
# Keys returning 401/403 are marked as invalid
rotator = APIKeyRotator(api_keys=["key1", "key2", "key3"])
# If key1 returns 401, it's automatically removed
```

### 2. Session Management
Secure session handling with connection pooling:

```python
# Sessions are automatically managed
rotator = APIKeyRotator(api_keys=["key1"])
# Session is created and configured securely
```

### 3. Timeout Configuration
Prevents hanging requests:

```python
rotator = APIKeyRotator(
    api_keys=["key1"],
    timeout=10.0  # Requests timeout after 10 seconds
)
```

### 4. SSL/TLS Verification
SSL certificate verification is enabled by default:

```python
# SSL verification is enabled by default
rotator = APIKeyRotator(api_keys=["key1"])

# Only disable for testing (not recommended in production)
response = rotator.get(url, verify=False)  # ⚠️ Not recommended
```

## 🔍 Security Audit

### Self-Audit Checklist

Before deploying to production, verify:

- [ ] API keys are stored in environment variables or secure storage
- [ ] No API keys are hardcoded in source code
- [ ] No API keys are committed to version control
- [ ] `.env` file is in `.gitignore`
- [ ] Logging level is set to INFO or WARNING in production
- [ ] SSL verification is enabled
- [ ] Timeouts are configured appropriately
- [ ] Error messages don't expose sensitive information
- [ ] Dependencies are up to date

### Automated Scanning

Consider using these tools:

```bash
# Check for secrets in code
pip install detect-secrets
detect-secrets scan

# Check for known vulnerabilities
pip install safety
safety check

# Keep dependencies updated
pip install pip-audit
pip-audit
```

## 📜 Security Updates

Security updates are released as patch versions (e.g., 0.4.1 → 0.4.2).

To stay informed:
- Watch the [GitHub repository](https://github.com/PrimeevolutionZ/apikeyrotator)
- Follow [@EclipsTeam](https://github.com/PrimeevolutionZ) on GitHub

## 🏆 Security Hall of Fame

We recognize and thank security researchers who responsibly disclose vulnerabilities:

<!-- Contributors will be listed here -->

*Want to be listed here? Report a valid security vulnerability!*

## 📚 Additional Resources

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

## 📞 Contact

For security-related questions (non-vulnerabilities):
- **GitHub Discussions**: [Security Category](https://github.com/PrimeevolutionZ/apikeyrotator/discussions)
- **General Contact**: develop@eclips-team.ru

For security vulnerabilities, always use the private reporting methods described above.

---

**Last Updated:** November 2025  
**Version:** 0.4.2

---

<div align="center">

**🛡️ Security is everyone's responsibility. Stay safe! 🛡️**

Made with 🔒 by [Eclips Team](https://github.com/PrimeevolutionZ)

</div>