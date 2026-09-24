# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.9.x | Yes (security fixes) |
| 0.8.x | Upgrade recommended (0.9.0 closes duplicate-execution risks for POST/PATCH) |
| 0.7.x | Upgrade recommended (last version supporting Python < 3.12) |
| < 0.7 | No, please upgrade (0.6.x removes working keys on 4xx responses) |

## Reporting a Vulnerability

**Do not open a public issue.** Report privately via
[GitHub Security Advisories](https://github.com/PrimeevolutionZ/apikeyrotator/security/advisories/new).

Please include: a description, the impact, affected versions, steps to reproduce
or a proof of concept, and (optionally) a suggested fix. Never include real API keys.

~~~text
Subject: [SECURITY] Brief description

Description / Impact / Affected versions / Steps to reproduce / Proof of concept / Suggested fix
~~~

**Response timeline:** first response within 48 hours, assessment within a week;
fixes for critical issues within 24-48 hours, high within a week, medium within two
weeks, low within a month. Disclosure is coordinated after a fixed release.

## Security Best Practices

### API Key Management

**Do**

- Keep keys in environment variables, `.env` files (git-ignored) or a secret manager.
- Use separate keys for development and production; rotate keys regularly.
- Load keys from a secret store and refresh them automatically:

```python
from apikeyrotator import APIKeyRotator, AWSSecretsManagerProvider

rotator = APIKeyRotator(
    secret_provider=AWSSecretsManagerProvider(secret_name="prod/api-keys"),
    auto_refresh_interval=900,   # pick up rotated keys every 15 minutes
)
```

**Don't**

- Hardcode keys in source code or commit `.env` files.
- Log `rotator.keys` or print keys - use `rotator.export_config()` (masked) instead.
- Share keys in tickets, chats or bug reports.

### Only send keys where they belong

The rotator adds an auth header with a key to **every** request it makes. Use a
rotator only for the API that issued its keys, never for arbitrary or
user-supplied URLs (e.g. scraping third-party sites).

Redirects: `requests` and `httpx` drop the `Authorization` header when redirected to
another host, but **not** custom headers such as `X-API-Key` (used automatically for
32-character keys or by your `header_callback`). For endpoints that may redirect
elsewhere, disable redirects:

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1"])
response = rotator.get("https://api.example.com/export", allow_redirects=False)
```

### Configuration File

`rotator_config.json` (or the `config_file` you pass) is only **read**, never written
by the library. Its `successful_headers` section is applied only with
`save_sensitive_headers=True`, and `Authorization` / `X-API-Key` entries in it are
always ignored. Don't put secrets in it.

### Shared State (Redis)

`RedisStateBackend` stores key **hashes** (SHA-256, or HMAC-SHA256 with `salt=`),
never raw keys. Still:

- use a password-protected Redis reachable only by your services (`rediss://` for TLS);
- set a `salt` when keys are short or guessable, so hashes can't be matched against
  known keys:

```python
import os
from apikeyrotator import RedisStateBackend

backend = RedisStateBackend(
    url=os.environ["REDIS_URL"],             # e.g. rediss://:password@redis:6380/0
    salt=os.environ["KEY_ID_SALT"].encode(),  # same value on all instances
)
```

### Proxies

Keep proxy credentials out of code:

```python
import os
from apikeyrotator import APIKeyRotator

proxy = f"http://{os.environ['PROXY_USER']}:{os.environ['PROXY_PASS']}@proxy.example.com:8080"
rotator = APIKeyRotator(api_keys=["key1"], proxy_list=[proxy])
```

### Logging

The library never logs raw keys - only a mask: the first and last 4 characters of keys
of 16+ characters (`sk-p...wxyz`, as API dashboards show them), the first 4 otherwise
(`sk-1****`) - and
prints nothing unless your application configures logging. At `DEBUG` level,
`LoggingMiddleware` logs request headers (secrets redacted) and JSON request bodies -
avoid `DEBUG` in production if bodies may contain personal data:

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("apikeyrotator").setLevel(logging.WARNING)
```

### TLS Verification

Certificate verification is on by default. To use a corporate CA, configure the
client instead of disabling verification:

```python
from apikeyrotator import APIKeyRotator

rotator = APIKeyRotator(api_keys=["key1"], http_client_kwargs={"verify": "/etc/ssl/corp-ca.pem"})
```

(`verify=False` per request works with the requests backend but is not recommended.)

## Security Features

- **Invalid keys are dropped**: keys answering `401`/`403` are removed from rotation
  (and, with a shared state backend, from all instances); background refresh does not
  re-add them.
- **Masking everywhere**: logs, `export_config()`, Prometheus labels and error messages
  show only the masked key (`sk-p...wxyz` / `sk-1****`).
- **No secrets at rest**: nothing is written to disk; Redis holds only key hashes.
- **Timeouts and deadlines**: `timeout` per attempt and `total_timeout` per request
  prevent hanging requests; the circuit breaker stops hammering failing hosts.
- **Safe retries**: non-idempotent requests are not replayed after the server may have
  executed them.

## Self-Audit Checklist

- [ ] Keys come from environment variables or a secret manager
- [ ] No keys in source code, git history or logs
- [ ] `.env` is in `.gitignore`
- [ ] Rotators are only used for the API that issued the keys
- [ ] Redirects disabled where custom auth headers could leak
- [ ] Logging at `INFO`/`WARNING` in production
- [ ] TLS verification enabled
- [ ] `timeout` / `total_timeout` configured
- [ ] Redis (if used) is private, authenticated, and a `salt` is set
- [ ] Dependencies are up to date

### Automated Scanning

```bash
pip install detect-secrets pip-audit
detect-secrets scan          # secrets in the code base
pip-audit                    # known vulnerabilities in dependencies
```

## Security Updates

Security fixes are released as patch versions (e.g. 0.8.0 → 0.8.1) and listed in the
[CHANGELOG](CHANGELOG.md). Watch the
[GitHub repository](https://github.com/PrimeevolutionZ/apikeyrotator) (Releases /
Security advisories) to be notified.

## Additional Resources

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [GitHub code security docs](https://docs.github.com/en/code-security)

---

**Last updated:** September 2026 · **Version:** 0.9.1
