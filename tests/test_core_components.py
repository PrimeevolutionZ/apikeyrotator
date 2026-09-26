"""
Tests of the core components in isolation and of the shared request engine,
driven directly (no HTTP client) - the engine is sans-IO: it yields effects and
the test plays the role of the driver.
"""

import asyncio
import logging
import threading

import pytest

from apikeyrotator import (
    AllKeysExhaustedError,
    APIKeyRotator,
    AsyncAPIKeyRotator,
    InMemoryStateBackend,
)
from apikeyrotator.core.engine import (
    AFTER,
    BEFORE,
    CALL,
    DONE,
    ON_ERROR,
    READ,
    RELEASE,
    SEND,
    SHORT,
    SLEEP,
    NetworkFailure,
)
from apikeyrotator.core.keys import KeyPool
from apikeyrotator.core.policy import RetryPolicy
from apikeyrotator.core.request_builder import RequestBuilder, infer_auth_header
from apikeyrotator.core.shared_state import StateSync
from apikeyrotator.middleware import ResponseInfo, RotatorMiddleware


LOG = logging.getLogger("test")


class Resp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.content = b"{}"
        self.closed = False

    def close(self):
        self.closed = True


def drive(flow, responses, sent=None):
    """Plays the driver: answers SEND with the next scripted response, records effects."""
    responses = iter(responses)
    effects = []
    value = None
    while True:
        effect = flow.send(value)
        effects.append(effect[0])
        tag = effect[0]
        if tag == SEND:
            if sent is not None:
                sent.append(effect[3]["headers"])
            value = next(responses)
            if isinstance(value, BaseException):
                value = NetworkFailure(value, safe_to_retry=True)
        elif tag in (DONE, SHORT):
            return effect[1], effects
        elif tag == CALL:
            value = effect[1](*effect[2])
        else:
            value = None


def make_rotator(**kwargs):
    kwargs.setdefault("api_keys", ["key_a", "key_b"])
    kwargs.setdefault("load_env_file", False)
    kwargs.setdefault("base_delay", 0.01)
    return APIKeyRotator(**kwargs)


class TestEngineDrivenDirectly:
    def test_success_is_a_single_send_then_done(self):
        engine = make_rotator()._engine
        ok = Resp(200)
        result, effects = drive(engine.run("GET", "https://api.example.com/x", {}), [ok])
        assert result is ok
        assert effects == [SEND, DONE]

    def test_retry_sleeps_and_releases_previous_failure(self):
        engine = make_rotator()._engine
        first, second, ok = Resp(503), Resp(503), Resp(200)
        result, effects = drive(engine.run("GET", "https://api.example.com/x", {}), [first, second, ok])
        assert result is ok
        assert effects.count(SEND) == 3
        assert effects.count(SLEEP) == 2
        # sync semantics: only the newest failed response stays open until the end
        assert effects.count(RELEASE) == 2

    def test_401_switches_key_without_consuming_an_attempt(self):
        rotator = make_rotator(max_retries=1)
        sent = []
        result, _ = drive(rotator._engine.run("GET", "https://api.example.com/x", {}),
                          [Resp(401), Resp(200)], sent)
        assert result.status_code == 200
        assert rotator.key_count == 1
        assert sent[0] != sent[1]  # a different key was used for the second attempt

    def test_network_error_not_retried_for_post(self):
        engine = make_rotator()._engine
        flow = engine.run("POST", "https://api.example.com/x", {})
        assert flow.send(None)[0] == SEND
        with pytest.raises(ConnectionError):
            flow.send(NetworkFailure(ConnectionError("reset"), safe_to_retry=False))

    def test_exhausted_after_max_retries(self):
        engine = make_rotator(max_retries=2)._engine
        with pytest.raises(AllKeysExhaustedError) as exc:
            drive(engine.run("GET", "https://api.example.com/x", {}), [Resp(500), Resp(500)])
        assert exc.value.last_response.status_code == 500

    def test_async_semantics_release_every_failed_response(self):
        rotator = AsyncAPIKeyRotator(api_keys=["key_a"], load_env_file=False, base_delay=0.01)
        engine = rotator._engine
        engine.status_of = lambda r: r.status_code
        result, effects = drive(engine.run("GET", "https://api.example.com/x", {}),
                                [Resp(503), Resp(200)])
        assert result.status_code == 200
        assert effects == [SEND, RELEASE, SLEEP, SEND, DONE]

    def test_short_circuit_middleware(self):
        class Cached(RotatorMiddleware):
            def before_request_sync(self, request_info):
                return ResponseInfo(status_code=200, headers={}, content=b"cached",
                                    request_info=request_info)

        engine = make_rotator(middlewares=[Cached()])._engine
        flow = engine.run("GET", "https://api.example.com/x", {})
        effect = flow.send(None)
        info = engine.chain.before_sync(effect[1], effect[2])
        effect = flow.send(info)
        assert effect[0] == SHORT and effect[1].content == b"cached"

    def test_exception_thrown_into_flow_releases_breaker_probe(self):
        rotator = make_rotator(circuit_breaker=True)
        flow = rotator._engine.run("GET", "https://api.example.com/x", {})
        flow.send(None)  # SEND - the breaker has granted this attempt
        with pytest.raises(KeyboardInterrupt):
            flow.throw(KeyboardInterrupt())
        assert rotator.get_circuit_states() == {"api.example.com": "CLOSED"}


class TestKeyPool:
    def test_strategy_is_created_on_first_keys(self):
        pool = KeyPool([], "round_robin", None, LOG)
        assert pool.strategy is None
        with pytest.raises(AllKeysExhaustedError):
            pool.select()
        pool.replace(["k1", "k2"])
        assert pool.strategy is not None
        assert {pool.select(), pool.select()} == {"k1", "k2"}

    def test_remove_updates_strategy(self):
        pool = KeyPool(["k1", "k2"], "round_robin", None, LOG)
        assert pool.remove("k1")
        assert not pool.remove("k1")
        assert {pool.select() for _ in range(4)} == {"k2"}

    def test_replace_keeps_metrics_of_kept_keys(self):
        pool = KeyPool(["k1", "k2"], "round_robin", None, LOG)
        pool.update("k1", True, 0.1)
        pool.replace(["k1", "k3"])
        assert pool.metrics_view()["k1"].total_requests == 1
        assert pool.metrics_view()["k3"].total_requests == 0

    def test_recovery_timeout_override(self):
        pool = KeyPool(["k1"], "round_robin", None, LOG, recovery_timeout=5)
        assert pool.recovery_timeout == 5


class TestRetryPolicy:
    def test_idempotency(self):
        policy = RetryPolicy()
        assert policy.is_idempotent("GET", None)
        assert not policy.is_idempotent("POST", None)
        assert policy.is_idempotent("POST", {"idempotency-key": "1"})
        assert RetryPolicy(retry_non_idempotent=True).is_idempotent("POST", None)

    def test_backoff_is_capped(self):
        policy = RetryPolicy(base_delay=1, max_delay=10)
        assert policy.backoff(0) <= 1.1
        assert policy.backoff(1000) <= 10

    def test_attempt_timeout_clipped_to_budget(self):
        policy = RetryPolicy(timeout=10)
        assert policy.attempt_timeout(None, None) == 10
        assert policy.attempt_timeout(3, None) == 3
        assert policy.attempt_timeout(None, 2.5) == 2.5
        assert policy.attempt_timeout(None, -1) == 0.001
        timeout_object = object()
        assert policy.attempt_timeout(timeout_object, 1) is None

    def test_invalid_max_retries(self):
        with pytest.raises(ValueError):
            RetryPolicy(max_retries=0)


class TestRequestBuilder:
    def test_auth_header_inference(self):
        assert infer_auth_header("sk-abc") == ("Authorization", "Bearer sk-abc")
        assert infer_auth_header("x" * 32) == ("X-API-Key", "x" * 32)
        assert infer_auth_header("plain") == ("Authorization", "Bearer plain")

    def test_auth_cache_is_bounded(self, monkeypatch):
        monkeypatch.setattr("apikeyrotator.core.request_builder._AUTH_CACHE_SIZE", 3)
        builder = RequestBuilder()
        for i in range(10):
            headers, _ = builder.headers_and_cookies(f"key{i}", None, "https://x")
            assert headers["Authorization"] == f"Bearer key{i}"
        assert len(builder._auth_cache) <= 3

    def test_user_agent_and_proxy_cycle(self):
        builder = RequestBuilder(user_agents=["a", "b"], proxy_list=["p1", "p2"])
        assert [builder.next_user_agent() for _ in range(3)] == ["a", "b", "a"]
        assert [builder.next_proxy() for _ in range(3)] == ["p1", "p2", "p1"]


class TestStateSync:
    def test_backend_failures_fail_open(self, caplog):
        class Broken(InMemoryStateBackend):
            def acquire_token(self, *args):
                raise ConnectionError("redis down")

            def report_invalid(self, *args):
                raise ConnectionError("redis down")

        pool = KeyPool(["k1"], "round_robin", None, LOG)
        state = StateSync(Broken(), 1.0, pool, LOG, on_invalid=pool.remove)
        assert state.acquire_token("k1", 1, 1.0) == 0.0
        reports = []
        state.report_invalid(reports, "k1")
        state.flush(reports)  # logged, not raised
        assert "redis down" in caplog.text

    def test_first_backend_error_is_logged_right_after_boot(self, caplog, monkeypatch):
        """time.monotonic() counts from boot: a fresh VM / CI runner starts near 0."""
        class Broken(InMemoryStateBackend):
            def acquire_token(self, *args):
                raise ConnectionError("redis down")

        monkeypatch.setattr("time.monotonic", lambda: 5.0)
        pool = KeyPool(["k1"], "round_robin", None, LOG)
        StateSync(Broken(), 1.0, pool, LOG, on_invalid=pool.remove).acquire_token("k1", 1, 1.0)
        assert "redis down" in caplog.text

    def test_backend_outage_keeps_token_buckets_locally_and_backs_off(self):
        calls = []

        class Broken(InMemoryStateBackend):
            def acquire_token(self, *args):
                calls.append(args)
                raise ConnectionError("redis down")

        pool = KeyPool(["k1"], "round_robin", None, LOG)
        state = StateSync(Broken(), 0.0, pool, LOG, on_invalid=pool.remove)
        assert [state.acquire_token("k1", 2, 0.001) == 0.0 for _ in range(3)] == [True, True, False]
        assert len(calls) == 1              # skipped during BACKEND_RETRY_INTERVAL
        assert not state.sync_due()         # no snapshot pulls either
        state._down_until = float('-inf')   # interval over: the backend is tried again
        state.acquire_token("k1", 2, 0.001)
        assert len(calls) == 2

    def test_key_ids_are_hashes(self):
        pool = KeyPool(["secret-key"], "round_robin", None, LOG)
        state = StateSync(None, 1.0, pool, LOG, on_invalid=pool.remove)
        assert "secret-key" not in state.key_id("secret-key")


class TestPublicAttributesReachComponents:
    def test_every_delegated_attribute_is_readable_and_writable(self):
        from apikeyrotator.core.rotator import BaseKeyRotator, _Delegate

        rotator = make_rotator()
        names = [n for n, v in vars(BaseKeyRotator).items() if isinstance(v, _Delegate)]
        assert "respect_rate_limit_headers" in names
        for name in names:
            setattr(rotator, name, getattr(rotator, name))   # AttributeError if mis-wired

    def test_setting_attributes_after_construction(self):
        rotator = make_rotator()
        rotator.max_retries = 7
        rotator.timeout = 3
        rotator.user_agents = ["UA"]
        assert rotator._policy.max_retries == 7
        assert rotator._policy.timeout == 3
        headers, _ = rotator._prepare_headers_and_cookies("key_a", None, "https://x")
        assert headers["User-Agent"] == "UA"


class _LoopBoundProvider:
    """A provider whose resources belong to the loop it was created in (like an aiohttp session)."""

    def __init__(self, keys=("k1", "k2")):
        self.loop = asyncio.get_running_loop()
        self.keys = list(keys)
        self.calls = 0

    async def get_keys(self):
        assert asyncio.get_running_loop() is self.loop, "provider used from a foreign event loop"
        self.calls += 1
        await asyncio.sleep(0)
        return list(self.keys)

    async def refresh_keys(self):
        return await self.get_keys()


class TestAsyncLazyProviderKeys:
    @pytest.mark.asyncio
    async def test_constructor_in_running_loop_does_not_call_provider(self):
        provider = _LoopBoundProvider()
        rotator = AsyncAPIKeyRotator(secret_provider=provider, load_env_file=False)
        assert provider.calls == 0
        assert rotator.keys == []
        assert await rotator.load_keys() == ["k1", "k2"]
        assert rotator.rotation_strategy is not None
        await rotator.close()

    @pytest.mark.asyncio
    async def test_async_with_loads_keys_once(self):
        provider = _LoopBoundProvider()
        async with AsyncAPIKeyRotator(secret_provider=provider, load_env_file=False) as rotator:
            assert rotator.keys == ["k1", "k2"]
            await asyncio.gather(*(rotator.load_keys() for _ in range(5)))
        assert provider.calls == 1

    @pytest.mark.asyncio
    async def test_first_request_loads_keys(self):
        from unittest.mock import AsyncMock, patch

        provider = _LoopBoundProvider(keys=["sk-lazy"])
        rotator = AsyncAPIKeyRotator(secret_provider=provider, load_env_file=False)
        sent = []

        async def fake_request(method, url, **kwargs):
            sent.append(kwargs["headers"])
            response = AsyncMock(status=200, headers={})
            response.release = AsyncMock()
            return response

        with patch("aiohttp.ClientSession.request", side_effect=fake_request):
            response = await rotator.get("https://api.example.com/x")
        assert response.status == 200
        assert sent[0]["Authorization"] == "Bearer sk-lazy"
        await rotator.close()

    @pytest.mark.asyncio
    async def test_provider_failure_is_raised_and_retried_later(self):
        provider = _LoopBoundProvider()
        original = provider.get_keys
        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("secret store unavailable")
            return await original()

        provider.get_keys = flaky
        rotator = AsyncAPIKeyRotator(secret_provider=provider, load_env_file=False)
        with pytest.raises(ConnectionError):
            await rotator.load_keys()
        assert await rotator.load_keys() == ["k1", "k2"]
        await rotator.close()

    @pytest.mark.asyncio
    async def test_empty_provider_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("LAZY_KEYS", "env1,env2")
        provider = _LoopBoundProvider(keys=[])
        rotator = AsyncAPIKeyRotator(secret_provider=provider, env_var="LAZY_KEYS", load_env_file=False)
        assert await rotator.load_keys() == ["env1", "env2"]
        await rotator.close()

    def test_outside_a_loop_keys_are_loaded_in_the_constructor(self, tmp_path):
        from apikeyrotator import FileSecretProvider

        path = tmp_path / "keys.txt"
        path.write_text("f1,f2")
        rotator = AsyncAPIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False)
        assert rotator.keys == ["f1", "f2"]


class TestEngineCleanupWithBlockingBackend:
    @staticmethod
    def _flow_with_pending_report():
        class BlockingBackend(InMemoryStateBackend):
            blocking = True  # like Redis: async rotators offload calls to a thread

        class Observer(RotatorMiddleware):
            pass

        backend = BlockingBackend(shared=True)
        rotator = AsyncAPIKeyRotator(api_keys=["key_a", "key_b"], load_env_file=False,
                                     state_backend=backend, middlewares=[Observer()])
        engine = rotator._engine
        engine.status_of = lambda r: r.status_code

        flow = engine.run("GET", "https://api.example.com/x", {})
        assert flow.send(None)[0] == CALL          # shared state pulled in a worker thread
        assert flow.send(backend.snapshot())[0] == BEFORE
        assert flow.send(None)[0] == SEND
        assert flow.send(Resp(429, {"Retry-After": "30"}))[0] == READ
        assert flow.send(b"")[0] == AFTER
        assert flow.send(None)[0] == ON_ERROR  # the 429 report is pending
        return flow, backend

    def test_pending_reports_are_flushed_when_a_middleware_fails(self):
        flow, backend = self._flow_with_pending_report()
        effect = flow.throw(RuntimeError("hook failed"))
        assert effect[0] == CALL                     # reports flushed off the event loop...
        effect[1](*effect[2])
        with pytest.raises(RuntimeError):            # ...then the exception continues
            flow.send(None)
        assert backend.snapshot().rate_limited       # the rate limit reached shared state

    @pytest.mark.parametrize("interrupt", [KeyboardInterrupt, asyncio.CancelledError, SystemExit])
    def test_cancellation_does_not_wait_for_the_backend(self, interrupt):
        flow, backend = self._flow_with_pending_report()
        with pytest.raises(interrupt):               # raised at once, no effect yielded
            flow.throw(interrupt())
        for thread in threading.enumerate():
            if thread.name == "apikeyrotator-flush":
                thread.join(5)
        assert backend.snapshot().rate_limited       # still reported, from a daemon thread


class TestAuthOption:
    @pytest.mark.parametrize("auth, key, expected", [
        (None, "sk-abc", ("Authorization", "Bearer sk-abc")),
        (None, "plain-key", ("Authorization", "Bearer plain-key")),
        (None, "x" * 32, ("X-API-Key", "x" * 32)),
        ("bearer", "x" * 32, ("Authorization", "Bearer " + "x" * 32)),
        ("x-api-key", "sk-abc", ("X-API-Key", "sk-abc")),
        (("Authorization", "Token {key}"), "abc", ("Authorization", "Token abc")),
        (("x-goog-api-key", "{key}"), "abc", ("x-goog-api-key", "abc")),
    ])
    def test_auth_modes(self, auth, key, expected):
        rotator = APIKeyRotator(api_keys=[key], load_env_file=False, auth=auth)
        headers, _ = rotator._prepare_headers_and_cookies(key, None, "https://x")
        assert headers == {expected[0]: expected[1]}

    def test_auth_false_sends_no_header(self):
        rotator = APIKeyRotator(api_keys=["abc"], load_env_file=False, auth=False)
        assert rotator._prepare_headers_and_cookies("abc", None, "https://x")[0] == {}

    def test_invalid_auth(self):
        with pytest.raises(ValueError, match="Unknown auth scheme"):
            APIKeyRotator(api_keys=["abc"], load_env_file=False, auth="basic")
        with pytest.raises(ValueError):
            APIKeyRotator(api_keys=["abc"], load_env_file=False, auth=("X-Key", "no placeholder"))

    def test_callback_sending_the_key_suppresses_default_header(self):
        rotator = APIKeyRotator(api_keys=["abc"], load_env_file=False,
                                header_callback=lambda key, h: {"x-goog-api-key": key})
        headers, _ = rotator._prepare_headers_and_cookies("abc", None, "https://x")
        assert headers == {"x-goog-api-key": "abc"}

    def test_auth_can_be_changed_later(self):
        rotator = APIKeyRotator(api_keys=["abc"], load_env_file=False)
        rotator.auth = "x-api-key"
        assert rotator._prepare_headers_and_cookies("abc", None, "https://x")[0] == {"X-API-Key": "abc"}


class TestRejectionsBeforeAuthIsConfirmed:
    def test_not_reported_to_shared_state_until_confirmed(self):
        backend = InMemoryStateBackend(shared=True)
        rotator = make_rotator(api_keys=["k1", "k2"], state_backend=backend)
        from apikeyrotator import AuthenticationError

        with pytest.raises(AuthenticationError):
            drive(rotator._engine.run("GET", "https://api.example.com/x", {}), [Resp(401), Resp(401)])
        assert backend.snapshot().invalid == set()   # other instances keep using the keys
        assert rotator.key_count == 2

    def test_async_rotator_behaves_the_same(self):
        from apikeyrotator import AuthenticationError

        rotator = AsyncAPIKeyRotator(api_keys=["k1", "k2"], load_env_file=False)
        engine = rotator._engine
        engine.status_of = lambda r: r.status_code
        with pytest.raises(AuthenticationError):
            drive(engine.run("GET", "https://api.example.com/x", {}), [Resp(403), Resp(403)])
        assert rotator.key_count == 2


class TestNoImplicitFileReads:
    def test_env_file_is_not_loaded_by_default(self, tmp_path, monkeypatch):
        from apikeyrotator import NoAPIKeysError

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DOTENV_KEYS", raising=False)
        (tmp_path / ".env").write_text("DOTENV_KEYS=from-dotenv\n")
        with pytest.raises(NoAPIKeysError, match="load_env_file=True"):
            APIKeyRotator(env_var="DOTENV_KEYS")
        assert "DOTENV_KEYS" not in __import__("os").environ

    def test_env_file_is_loaded_on_request(self, tmp_path, monkeypatch):
        pytest.importorskip("dotenv")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DOTENV_KEYS", raising=False)
        (tmp_path / ".env").write_text("DOTENV_KEYS=from-dotenv\n")
        try:
            assert APIKeyRotator(env_var="DOTENV_KEYS", load_env_file=True).keys == ["from-dotenv"]
        finally:
            __import__("os").environ.pop("DOTENV_KEYS", None)

    def test_config_file_in_cwd_is_ignored_unless_given(self, tmp_path, monkeypatch):
        import json

        monkeypatch.chdir(tmp_path)
        (tmp_path / "rotator_config.json").write_text(json.dumps(
            {"successful_headers": {"x": {"X-Extra": "1"}}}))
        assert APIKeyRotator(api_keys=["k"], save_sensitive_headers=True).config == {}
        explicit = APIKeyRotator(api_keys=["k"], save_sensitive_headers=True,
                                 config_file="rotator_config.json")
        assert explicit._prepare_headers_and_cookies("k", None, "https://x/")[0]["X-Extra"] == "1"


class TestSyncAsyncConsistency:
    def test_should_retry_callback_gets_the_response_in_async_too(self):
        seen = []
        rotator = AsyncAPIKeyRotator(api_keys=["k1"], load_env_file=False, base_delay=0.01,
                                     should_retry_callback=lambda r: seen.append(r) or False)
        engine = rotator._engine
        engine.status_of = lambda r: r.status_code
        ok = Resp(200)
        drive(engine.run("GET", "https://api.example.com/x", {}), [ok])
        assert seen == [ok]

    def test_sync_rotator_warns_about_async_only_middleware(self):
        class AsyncOnly(RotatorMiddleware):
            async def before_request(self, request_info):
                return request_info

        with pytest.warns(UserWarning, match="before_request_sync"):
            APIKeyRotator(api_keys=["k1"], middlewares=[AsyncOnly()])

    def test_no_warning_for_sync_or_complete_middlewares(self, recwarn):
        from apikeyrotator import CachingMiddleware, LoggingMiddleware, RateLimitMiddleware

        APIKeyRotator(api_keys=["k1"], middlewares=[
            CachingMiddleware(), LoggingMiddleware(), RateLimitMiddleware()])
        assert not [w for w in recwarn if issubclass(w.category, UserWarning)]

    @pytest.mark.asyncio
    async def test_async_rotator_runs_sync_hooks_of_duck_typed_middleware(self):
        calls = []

        class SyncOnly:  # not a RotatorMiddleware subclass
            def before_request_sync(self, request_info):
                calls.append("before")
                return request_info

        chain = AsyncAPIKeyRotator(api_keys=["k1"], middlewares=[SyncOnly()])._chain
        from apikeyrotator.middleware import RequestInfo

        info = RequestInfo(method="GET", url="https://x", headers={}, cookies={}, key="k1",
                           attempt=0, kwargs={})
        assert await chain.before(info, {}) is None
        assert calls == ["before"]
