# Contributing to APIKeyRotator

Thank you for your interest in contributing! Bug fixes, features, tests and
documentation improvements are all welcome.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Architecture](#architecture)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Performance Changes](#performance-changes)
- [Documentation](#documentation)
- [Release Process](#release-process)

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on what is best for the community
- Accept constructive criticism gracefully

## Development Setup

Prerequisites: **Python 3.12+**, Git, a GitHub account.

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/apikeyrotator.git
cd apikeyrotator
git remote add upstream https://github.com/PrimeevolutionZ/apikeyrotator.git

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev,test]"       # library + pytest, ruff, mypy, httpx, fakeredis...

pytest                             # ~2 seconds, no network needed
ruff check .
```

## How to Contribute

- **Issues** labelled `good first issue`, `help wanted`, `bug`, `enhancement`:
  [open issues](https://github.com/PrimeevolutionZ/apikeyrotator/issues).
- **Features**: open a GitHub Discussion or an issue first for API changes.
- **Security issues**: do not open a public issue - see [SECURITY.md](SECURITY.md).

### Bug Report Template

~~~markdown
**Describe the bug**
What happened and what you expected.

**To reproduce**
```python
from apikeyrotator import APIKeyRotator
rotator = APIKeyRotator(api_keys=["key1"])
...
```

**Environment**
- OS, Python version (e.g. 3.12.3)
- apikeyrotator version (`python -c "import apikeyrotator; print(apikeyrotator.__version__)"`)
- HTTP backend (requests / aiohttp / httpx) and its version

**Traceback / logs**
Run with `logging.basicConfig(level=logging.DEBUG)`; keys are masked in logs,
but double-check before pasting.
~~~

### Feature Request Template

~~~markdown
**Problem**
What problem does this solve?

**Proposed API**
```python signature
rotator = APIKeyRotator(api_keys=[...], new_option=True)
```

**Alternatives considered**
~~~

## Pull Request Process

1. **Branch** from an up-to-date `master`:

   ```bash
   git checkout master && git pull upstream master
   git checkout -b feature/amazing-feature   # or fix/..., docs/..., test/..., refactor/..., perf/...
   ```

2. **Change** the code, add tests, update docs and `CHANGELOG.md`.

3. **Check locally** - the same checks run in CI (`.github/workflows/ci.yml`):

   ```bash
   ruff check .
   pytest --cov=apikeyrotator
   python benchmarks/bench_core.py --quick          # benchmark still runs
   python scripts/check_docs.py                     # doc examples match the API
   ```

4. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/) style:

   ```text
   feat: add failover rotation strategy
   fix: release half-open circuit probe when an attempt dies
   docs: update middleware guide
   perf: single-pass rate-limit header parsing
   ```

5. **Push and open a PR** describing *what* and *why*, how it was tested, and linking
   issues (`Closes #123`). CI runs lint, tests on Python 3.12/3.13 and a benchmark of
   your branch against `master`.

6. **Review**: address comments; keep the branch up to date with
   `git fetch upstream && git merge upstream/master` (or rebase if you prefer).

## Architecture

The rotators are thin facades over small components in `apikeyrotator/core/`:

| Module | Component | Responsibility |
|---|---|---|
| `rotator.py` | `APIKeyRotator`, `AsyncAPIKeyRotator` | Public API; assembles the components; *drives* the request loop (blocking / asyncio I/O) |
| `engine.py` | `RequestEngine` | The request loop, written once for both rotators (see below) |
| `keys.py` | `KeyPool` | Active keys, per-key metrics, rotation strategy, key removal |
| `policy.py` | `RetryPolicy` | Attempts, backoff, timeouts and deadline, idempotency rules |
| `limits.py` | `RateLimiter` | Token buckets, 429 / `X-RateLimit-*` handling |
| `breakers.py` | `BreakerRegistry` | Per-host circuit breakers |
| `shared_state.py` | `StateSync` | Sync with a `StateBackend` (Redis), fail-open |
| `request_builder.py` | `RequestBuilder` | Auth header, custom headers/cookies, user agent and proxy rotation |
| `middleware_chain.py` | `MiddlewareChain` | Runs middleware hooks in list order |
| `transport.py` | `*Transport` | HTTP clients (requests, aiohttp, httpx) behind one interface |

**The request engine is sans-IO.** `RequestEngine.run()` is a generator: it makes every
decision and *yields* the I/O it needs as effects (`SEND`, `SLEEP`, `READ`, `RELEASE`,
middleware hooks, blocking state-backend `CALL`s) and finishes with `DONE`/`SHORT`. The sync
rotator performs the effects with blocking calls, the async rotator awaits them. So:

- a new request-level feature is implemented **once** in `engine.py` (plus a component if
  it has state) and works in both rotators;
- the engine can be tested without any HTTP client by sending responses into the generator
  (see `tests/test_core_components.py`);
- a new public constructor argument goes to the component it configures; expose it on the
  rotator with `_Delegate` so that changing the attribute later reaches the component.

## Coding Standards

- **Style**: `ruff check .` must pass (rules configured in `pyproject.toml`: pyflakes,
  import sorting, pyupgrade for 3.12+, bugbear). Line length 100.
- **Type hints** on public functions, modern syntax:

  ```python
  def get_keys(api_keys: list[str] | None = None) -> list[str]:
      """Get API keys from various sources."""
  ```

- **Docstrings**: Google style (`Args:`, `Returns:`, `Raises:`).
- **Errors**: raise specific exceptions (subclasses of `APIKeyError` for library
  errors); never swallow exceptions silently.
- **Logging**: `logger = logging.getLogger(__name__)`; never add handlers or set
  levels in library code; never log raw API keys (use `apikeyrotator.core.util.mask_key`).
  Use `%`-style arguments in hot paths (`logger.debug("key %s", masked)`).
- **Thread safety**: rotators are shared between threads; guard shared mutable state.
- **Optional dependencies** (httpx, redis, boto3, google-cloud) are imported lazily.

## Testing Guidelines

- Tests live in `tests/`, named `test_<topic>.py`; no real network access.
- Sync requests: patch `requests.Session.request` or use the `requests_mock` fixture.
- Async requests: patch `aiohttp.ClientSession.request` (`aioresponses` does not support
  aiohttp 3.14+).
- httpx backend: `http_client_kwargs={"transport": httpx.MockTransport(handler)}`.
- Time-dependent logic (backoff, rate limits, circuit breaker, deadlines): use the
  `virtual_clock` fixture from `tests/conftest.py` - sleeps are instant, the clock advances.
- Redis: the `fakeredis` package (`redis_client` fixture in `tests/test_features.py`).

```python
from unittest.mock import Mock, patch
from apikeyrotator import APIKeyRotator

def test_switches_key_on_429(virtual_clock):
    rotator = APIKeyRotator(api_keys=["k1", "k2"])
    with patch("requests.Session.request") as request:
        request.side_effect = [
            Mock(status_code=429, headers={"Retry-After": "30"}, content=b""),
            Mock(status_code=200, headers={}, content=b"{}"),
        ]
        assert rotator.get("https://api.example.com").status_code == 200
    assert virtual_clock.sleeps == []   # switched immediately, no waiting
```

```python
from unittest.mock import AsyncMock, patch

import pytest
from apikeyrotator import AsyncAPIKeyRotator

@pytest.mark.asyncio
async def test_async_get():
    response = AsyncMock(status=200, headers={})
    response.json = AsyncMock(return_value={"ok": True})
    async with AsyncAPIKeyRotator(api_keys=["k1"]) as rotator:
        with patch("aiohttp.ClientSession.request", AsyncMock(return_value=response)):
            result = await rotator.get("https://api.example.com/data")
            assert await result.json() == {"ok": True}
```

```bash
pytest                                  # all tests
pytest tests/test_features.py -v        # one file
pytest -k circuit                       # by name
pytest --cov=apikeyrotator --cov-report=html
```

## Performance Changes

Changes to the core (`apikeyrotator/core`, `strategies`, `middleware`, `metrics`)
should be checked with the benchmark:

```bash
git stash && python benchmarks/bench_core.py --save /tmp/before.json && git stash pop
python benchmarks/bench_core.py --compare /tmp/before.json --threshold 10
```

The PR benchmark job fails on regressions of machine-independent metrics (upstream
calls, waiting time, success rate, memory). See [benchmarks/README.md](benchmarks/README.md).

## Documentation

- User docs live in `docs/`, the API reference in `docs/API_REFERENCE.md`.
- Every Python example must run against the current API. `scripts/check_docs.py`
  verifies imports, parameters, methods and links in all Markdown files (also in CI).
  Fence non-runnable signatures as ` ```python signature `.
- Keep examples short and never put real keys in docs.

## Release Process

Releases are automated (`.github/workflows/release.yml`, called by CI):

1. Bump the version in `pyproject.toml` **and** `apikeyrotator/__init__.py` (`__version__`) -
   the release job fails if they differ.
2. Add a `## [X.Y.Z] - date` section to `CHANGELOG.md` (it becomes the release notes).
3. Merge to `master`. When lint, docs and tests pass, CI creates the tag `X.Y.Z` (tags have
   no `v` prefix) and a GitHub release with the wheel and the sdist. A version that is
   already tagged is skipped, so ordinary merges don't release anything.

Alternatives: push a tag yourself (`git tag -a 0.9.1 -m "apikeyrotator 0.9.1" && git push
origin 0.9.1` - CI runs on tags too, and the tag must match the package version), or run
**Actions → Release → Run workflow** for any commit.

PyPI publishing is opt-in: add a [trusted publisher](https://docs.pypi.org/trusted-publishers/)
on PyPI for this repository (workflow `release.yml`, environment `pypi`) and set the repository
variable `PYPI_PUBLISH=true`.

Versions follow [Semantic Versioning](https://semver.org/). Before 1.0, minor versions
(`0.7 → 0.8`) may contain breaking changes; they are listed in the changelog.

## Getting Help

Ask in [GitHub Discussions](https://github.com/PrimeevolutionZ/apikeyrotator/discussions).

## License

By contributing, you agree that your contributions are licensed under the MIT License.

---

<div align="center">

**Thank you for contributing to APIKeyRotator! **

</div>
