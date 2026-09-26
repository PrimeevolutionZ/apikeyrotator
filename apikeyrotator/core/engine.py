"""
The request loop, written once for sync and async rotators.

``RequestEngine.run()`` is a generator ("sans-IO"): it makes every decision -
which key, retry or not, how long to wait, what to record - and *yields* the
I/O it needs as effects. The rotators are thin drivers: ``APIKeyRotator``
performs an effect with blocking calls, ``AsyncAPIKeyRotator`` awaits it, and
both send the result back into the generator. A feature added here therefore
works in both rotators and is tested once.

Effects are tuples ``(TAG, *args)``:

========  ==============================================  =================================
tag       arguments                                       result sent back
========  ==============================================  =================================
SEND      method, url, request_kwargs, proxy, timeout     response or NetworkFailure
READ      response                                        body bytes or NetworkFailure
RELEASE   response                                        None (connection back to the pool)
SLEEP     seconds                                         None
BEFORE    request_info, request_kwargs                    ResponseInfo (short-circuit) or None
AFTER     response_info                                   None
ON_ERROR  error_info                                      None
CALL      fn, args                                        fn(*args) - blocking state-backend I/O
DONE      response                                        - (the driver returns the response)
SHORT     response_info, url                              - (the driver returns a response built
                                                          from a middleware short-circuit)
========  ==============================================  =================================

The flow always ends with DONE or SHORT (or an exception) after its cleanup has
run - the driver then drops the generator. Ending with an effect instead of a
``return`` saves raising StopIteration on every request.

Exceptions raised while performing an effect (other than network errors, which
come back as NetworkFailure) are thrown into the generator, so its cleanup
(circuit breaker probe release, state reports) always runs.
"""

from __future__ import annotations
import logging
import threading
import time
import uuid
from collections.abc import Callable, Generator
from enum import Enum
from typing import Any

from apikeyrotator.metrics import RotatorMetrics
from apikeyrotator.middleware import ErrorInfo, ResponseInfo
from apikeyrotator.utils import (
    CircuitBreaker,
    ErrorClassifier,
    ErrorType,
    get_header,
    parse_retry_after,
)

from .breakers import BreakerRegistry
from .exceptions import (
    AllKeysExhaustedError,
    AuthenticationError,
    CircuitOpenError,
    DeadlineExceededError,
    HTTPStatusError,
)
from .keys import KeyPool
from .limits import RateLimiter
from .middleware_chain import MiddlewareChain
from .policy import NON_IDEMPOTENT_RETRYABLE_STATUSES, RetryPolicy
from .request_builder import RequestBuilder
from .responses import StatusView, UnifiedResponse
from .shared_state import Report, StateSync
from .util import endpoint_label, host_of, mask_key, unique_labels


SEND, DONE, SHORT, READ, RELEASE, SLEEP, BEFORE, AFTER, ON_ERROR, CALL = range(10)

Effect = tuple
Flow = Generator[Effect, Any, Any]


class NetworkFailure:
    """Result of SEND/READ when the transport raised one of its network errors."""
    __slots__ = ('error', 'safe_to_retry')

    def __init__(self, error: Exception, safe_to_retry: bool):
        self.error = error
        #: True if the request certainly never reached the server (e.g. connection refused)
        self.safe_to_retry = safe_to_retry


class Action(Enum):
    """What the request loop does after a response was classified."""
    RETURN = "return"  # hand the response to the caller
    RETRY = "retry"  # retry (consumes one attempt)
    SWITCH = "switch"  # key was rejected, retry with another key (no attempt consumed)
    AUTH_FAILED = "auth_failed"  # every key rejected before any success - raise AuthenticationError


class RequestContext:
    """Per-request state of the retry loop."""
    __slots__ = (
        'method', 'url', 'endpoint', 'idempotent', 'deadline', 'attempt',
        'last_response', 'last_exception', 'reports', 'breaker', 'breaker_pending', 'rejected',
        'unsafe_method', 'possibly_processed', 'pinned_key',
    )

    def __init__(self, method: str, url: str, idempotent: bool, deadline: float | None,
                 breaker: CircuitBreaker | None):
        self.method = method
        self.url = url
        self.endpoint = endpoint_label(url)
        self.idempotent = idempotent
        self.deadline = deadline
        self.attempt = 0
        self.last_response: Any = None
        self.last_exception: BaseException | None = None
        # Deferred writes to the state backend, flushed between attempts
        self.reports: list[Report] = []
        self.breaker = breaker
        # True between allow_request() and a verdict (success/failure): if the attempt
        # dies in between, the HALF_OPEN probe slot must be released.
        self.breaker_pending = False
        # Keys rejected with 401/403 in this request while auth is not confirmed yet
        self.rejected: dict[str, int] | None = None  # key -> status, in attempt order
        #: POST/PATCH...: every call may change state on the server
        self.unsafe_method = False
        #: An attempt of an unsafe request may have been executed (5xx, read timeout...)
        self.possibly_processed = False
        #: Key of that attempt: retries reuse it, because idempotency keys are usually
        #: scoped to the account of the API key
        self.pinned_key: str | None = None

    def breaker_verdict(self, success: bool) -> None:
        breaker = self.breaker
        if breaker is not None:
            self.breaker_pending = False
            if success:
                breaker.record_success()
            else:
                breaker.record_failure()

    def release_breaker(self) -> None:
        breaker = self.breaker
        if self.breaker_pending and breaker is not None:
            self.breaker_pending = False
            breaker.release_probe()

    def remaining(self) -> float | None:
        if self.deadline is None:
            return None
        return self.deadline - time.monotonic()


class RequestEngine:
    """
    Orchestrates one request over the rotator's components:

    - KeyPool: which key (rotation strategy), per-key metrics, key removal
    - RetryPolicy: attempts, backoff, timeouts, idempotency
    - RateLimiter: token buckets, 429 / rate-limit headers
    - BreakerRegistry: per-host circuit breakers
    - StateSync: shared state between processes
    - RequestBuilder: auth header, headers/cookies, user agent, proxy
    - MiddlewareChain: hooks (performed by the driver)
    """

    __slots__ = ('pool', 'policy', 'limiter', 'breakers', 'state', 'builder', 'chain',
                 'metrics', 'classifier', 'logger', 'sync', 'status_of', 'unified')

    def __init__(self, *, pool: KeyPool, policy: RetryPolicy, limiter: RateLimiter,
                 breakers: BreakerRegistry, state: StateSync, builder: RequestBuilder,
                 chain: MiddlewareChain, metrics: RotatorMetrics | None,
                 classifier: ErrorClassifier, logger: logging.Logger, sync: bool):
        self.pool = pool
        self.policy = policy
        self.limiter = limiter
        self.breakers = breakers
        self.state = state
        self.builder = builder
        self.chain = chain
        self.metrics = metrics
        self.classifier = classifier
        self.logger = logger
        #: Sync semantics: the classifier and should_retry_callback get the response
        #: object, the newest failed response is kept open, a timeout is always passed.
        self.sync = sync
        self.status_of: Callable[[Any], int] = lambda response: response.status_code
        #: unified_response=True: every response is read and returned as UnifiedResponse
        self.unified = False

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def run(self, method: str, url: str, kwargs: dict[str, Any]) -> Flow:
        """Generator performing one request; ends with a DONE or SHORT effect."""
        policy = self.policy
        pool = self.pool
        limiter = self.limiter
        state = self.state
        builder = self.builder
        middlewares = self.chain.middlewares
        sync = self.sync
        # Async rotators run blocking backend calls (Redis) in a worker thread
        offload = not sync and state.blocking
        stream = sync and bool(kwargs.get("stream"))
        unified = self.unified
        if unified and kwargs.get("stream"):
            raise ValueError("stream=True needs the client's own response; it is not supported "
                             "with unified_response=True")
        # Native responses hold a connection until released; unified ones don't
        release_native = not unified

        method_upper = method.upper()
        unsafe_method = policy.is_unsafe_method(method_upper)
        idempotency_header = policy.idempotency_header
        if idempotency_header and unsafe_method \
                and get_header(kwargs.get("headers"), idempotency_header) is None:
            # One key per logical request, identical on every retry
            kwargs["headers"] = {**(kwargs.get("headers") or {}), idempotency_header: uuid.uuid4().hex}
        ctx = RequestContext(
            method, url,
            policy.is_idempotent(method_upper, kwargs.get("headers")),
            policy.deadline(kwargs.pop("total_timeout", policy.total_timeout)),
            self.breakers.for_url(url),
        )
        ctx.unsafe_method = unsafe_method
        if state.sync_due():
            yield from self._pull_state(offload)

        result = short_circuit = None
        try:
            while True:
                self._check_budget(ctx)
                self._check_breaker(ctx)

                key = self._select(ctx)
                if limiter.key_rate_limit is not None:
                    while True:
                        wait = (yield (CALL, limiter.bucket_wait, (key,))) if offload \
                            else limiter.bucket_wait(key)
                        if wait <= 0:
                            break
                        if ctx.pinned_key is not None:
                            # The pinned key must be reused: wait for its own token
                            yield from self._sleep(ctx, min(wait, policy.max_delay))
                            continue
                        yield from self._sleep(ctx, limiter.after_bucket_denied(key, wait))
                        if pool.count() == 0:
                            raise AllKeysExhaustedError("All keys are invalid (empty list)")
                        key = self._select(ctx)
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("Selected key: %s", mask_key(key))

                request_kwargs, request_info = builder.build(
                    method, url, key, kwargs, ctx.attempt, bool(middlewares)
                )
                if middlewares:
                    short_circuit = yield (BEFORE, request_info, request_kwargs)
                    if short_circuit is not None:
                        break

                if policy.random_delay_range:
                    yield from self._sleep(ctx, policy.random_delay())

                user_timeout = kwargs.get("timeout")
                # Async sessions already carry the default timeout - pass one only when it differs
                if sync or ctx.deadline is not None or user_timeout is not None:
                    timeout = policy.attempt_timeout(user_timeout, ctx.remaining())
                else:
                    timeout = None

                start = time.monotonic()
                response = yield (SEND, method, url, request_kwargs, builder.next_proxy(), timeout)
                if response.__class__ is NetworkFailure:
                    yield from self._network_failure(ctx, key, response, start, request_info)
                    continue
                request_time = time.monotonic() - start
                status = response.status_code if sync else self.status_of(response)
                headers = response.headers

                content = None
                if (middlewares or unified) and not stream:
                    # Middlewares (e.g. caching) and unified responses need the body; clients
                    # cache it, so the caller can still read a native response.
                    content = yield (READ, response)
                    if content.__class__ is NetworkFailure:
                        yield (RELEASE, response)
                        yield from self._network_failure(ctx, key, content, start, request_info)
                        continue
                if unified:
                    # The body is fully read, so every client has already returned the
                    # connection to its pool - no RELEASE needed
                    response = UnifiedResponse.from_native(response, status, content, request_time)

                response_info = None
                if middlewares:
                    assert request_info is not None   # BEFORE ran: middlewares are present
                    response_info = ResponseInfo(
                        status_code=status, headers=dict(headers), content=content,
                        request_info=request_info, response_time=request_time,
                    )
                    yield (AFTER, response_info)

                action, error_type = self._evaluate(ctx, key, status, headers, response, request_time)

                if action is Action.RETURN:
                    if sync and release_native and ctx.last_response is not None:
                        yield (RELEASE, ctx.last_response)
                    result = response
                    break

                if response_info is not None:
                    yield (ON_ERROR, ErrorInfo(
                        exception=HTTPStatusError(status),
                        request_info=response_info.request_info, response_info=response_info,
                    ))

                if not release_native:
                    pass
                elif sync:
                    # Keep only the newest failed response open - it is exposed via
                    # AllKeysExhaustedError.last_response
                    if ctx.last_response is not None:
                        yield (RELEASE, ctx.last_response)
                else:
                    # Async connections go back to the pool immediately; the response
                    # object is still exposed via AllKeysExhaustedError
                    yield (RELEASE, response)
                ctx.last_response = response
                ctx.last_exception = None

                if action is Action.AUTH_FAILED:
                    raise self._auth_error(ctx)
                if action is Action.RETRY:
                    ctx.attempt += 1
                if ctx.reports:
                    yield from self._flush(ctx, offload)
                if action is Action.RETRY and ctx.attempt < policy.max_retries:
                    yield from self._sleep(ctx, self._retry_delay(ctx, error_type, headers))
        except GeneratorExit:  # driver dropped the flow mid-request - no more effects possible
            ctx.release_breaker()
            raise
        except BaseException as exc:
            if ctx.possibly_processed and isinstance(exc, AllKeysExhaustedError):
                exc.possibly_processed = True
            ctx.release_breaker()
            if ctx.reports:
                if isinstance(exc, Exception):
                    yield from self._flush(ctx, offload)
                else:
                    # Cancellation / KeyboardInterrupt / SystemExit must not wait for Redis
                    self._flush_detached(ctx)
            raise
        ctx.release_breaker()
        if ctx.reports:
            yield from self._flush(ctx, offload)
        if short_circuit is not None:
            yield (SHORT, short_circuit, url)
        yield (DONE, result)

    # ------------------------------------------------------------------
    # Effects helpers
    # ------------------------------------------------------------------

    def _sleep(self, ctx: RequestContext, delay: float) -> Flow:
        if delay > 0:
            self._check_deadline(ctx, delay)
            yield (SLEEP, delay)

    def _pull_state(self, offload: bool) -> Flow:
        state = self.state
        backend = state.backend
        assert backend is not None   # only called when the backend is shared
        try:
            if offload:
                snapshot = yield (CALL, backend.snapshot, ())
            else:
                snapshot = backend.snapshot()
        except Exception as e:
            state.log_error("snapshot", e)
            return
        state.apply(snapshot)

    def _flush(self, ctx: RequestContext, offload: bool) -> Flow:
        reports, ctx.reports = ctx.reports, []
        if offload:
            yield (CALL, self.state.flush, (reports,))
        else:
            self.state.flush(reports)

    def _flush_detached(self, ctx: RequestContext) -> None:
        """Sends pending reports without blocking the caller (a daemon thread for network backends)."""
        reports, ctx.reports = ctx.reports, []
        state = self.state
        if state.blocking:
            threading.Thread(target=state.flush, args=(reports,), name="apikeyrotator-flush",
                             daemon=True).start()
        else:
            state.flush(reports)

    def _network_failure(self, ctx: RequestContext, key: str, failure: NetworkFailure,
                         start: float, request_info: Any) -> Flow:
        request_time = time.monotonic() - start
        error = failure.error
        if request_info is not None:
            yield (ON_ERROR, ErrorInfo(exception=error, request_info=request_info))
        if not self._record_network_error(ctx, key, error, request_time, failure.safe_to_retry):
            raise error
        if ctx.attempt < self.policy.max_retries:
            yield from self._sleep(ctx, self.policy.backoff(ctx.attempt - 1))

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_deadline(self, ctx: RequestContext, delay: float = 0.0) -> None:
        """Raises DeadlineExceededError if the budget is spent (or would be by waiting `delay`)."""
        remaining = ctx.remaining()
        if remaining is not None and (remaining <= 0 or delay >= remaining):
            raise DeadlineExceededError(
                f"Request deadline exceeded after {ctx.attempt} attempt(s)",
                last_response=ctx.last_response, last_exception=ctx.last_exception,
            )

    def _check_budget(self, ctx: RequestContext) -> None:
        if ctx.attempt >= self.policy.max_retries:
            raise self.exhausted_error(ctx.last_response, ctx.last_exception)
        if self.pool.count() == 0:
            raise AllKeysExhaustedError(
                "All keys are invalid (empty list)",
                last_response=ctx.last_response, last_exception=ctx.last_exception,
            )
        self._check_deadline(ctx)

    def _check_breaker(self, ctx: RequestContext) -> None:
        breaker = ctx.breaker
        if breaker is None:
            return
        if breaker.allow_request():
            ctx.breaker_pending = True
        else:
            raise CircuitOpenError(
                host_of(ctx.url), breaker.retry_after(),
                last_response=ctx.last_response, last_exception=ctx.last_exception,
            )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def _record(self, key: str, endpoint: str, success: bool, request_time: float,
                is_rate_limited: bool = False, key_success: bool | None = None) -> None:
        metrics = self.metrics
        if metrics is not None:
            metrics.record_request(
                key=key, endpoint=endpoint, success=success,
                response_time=request_time, is_rate_limited=is_rate_limited
            )
        self.pool.update(key, success if key_success is None else key_success, request_time, is_rate_limited)

    def _evaluate(self, ctx: RequestContext, key: str, status_code: int, headers: Any,
                  response: Any, request_time: float) -> tuple[Action, ErrorType | None]:
        """Classifies a response, records it and decides what the loop does next."""
        if self.sync or self.unified:
            classifier_response = callback_arg = response
        else:
            classifier_response, callback_arg = StatusView(status_code, headers), response
        endpoint = ctx.endpoint
        policy = self.policy
        classifier = self.classifier
        error_type = classifier.classify_error(response=classifier_response)

        # Host health: 5xx = failure, anything else (incl. 4xx/429) = host is alive
        ctx.breaker_verdict(status_code < 500)

        if error_type == ErrorType.PERMANENT:
            if classifier.should_remove_key(classifier_response):
                self._record(key, endpoint, False, request_time)
                pool = self.pool
                if not pool.auth_confirmed:
                    # Nothing has succeeded yet: the auth header format may be wrong for
                    # every key. Keep the key for now and try the others.
                    pool.add_suspect(key, status_code)
                    rejected = ctx.rejected
                    if rejected is None:
                        rejected = ctx.rejected = {}
                    rejected[key] = status_code
                    if len(rejected) >= pool.count():
                        # Every key was refused - the header is wrong, so none of them is
                        # "known invalid": they must not be removed once a request succeeds
                        pool.clear_suspects()
                        return Action.AUTH_FAILED, error_type
                    self.logger.warning(
                        f"Key {mask_key(key)} rejected (status {status_code}) before any request "
                        f"succeeded; trying another key")
                    return Action.SWITCH, error_type
                self._remove_invalid(ctx, key, status_code)
                return Action.SWITCH, error_type
            # Client error (400/404/422...) - the request is wrong, not the key.
            # Retrying or removing the key would not help: hand the response back.
            self._record(key, endpoint, False, request_time, key_success=True)
            if not self.pool.auth_confirmed:
                self._confirm_auth(ctx)
            self.logger.warning(f"Client error (status {status_code}), not retrying")
            return Action.RETURN, error_type

        if error_type in (ErrorType.RATE_LIMIT, ErrorType.TEMPORARY):
            is_rate_limited = error_type == ErrorType.RATE_LIMIT
            self._record(key, endpoint, False, request_time, is_rate_limited=is_rate_limited)
            if is_rate_limited:
                self.limiter.on_rate_limited(ctx.reports, key, headers, ctx.attempt)
            if not policy.may_retry_status(ctx.idempotent, status_code):
                # The server may already have processed this POST/PATCH - retrying could
                # duplicate the operation. Hand the response to the caller instead.
                self.logger.warning(
                    f"{ctx.method} got {status_code}; not retrying a non-idempotent request "
                    f"(pass retry_non_idempotent=True or an Idempotency-Key header to allow it)")
                return Action.RETURN, error_type
            if ctx.unsafe_method and status_code not in NON_IDEMPOTENT_RETRYABLE_STATUSES:
                self._mark_possibly_processed(ctx, key)
            msg = "Rate limited" if is_rate_limited else "Temporary error"
            self.logger.warning(
                f"{msg} (status {status_code}, key {mask_key(key)}). "
                f"Attempt {ctx.attempt + 1}/{policy.max_retries}")
            return Action.RETRY, error_type

        callback = policy.should_retry_callback
        if callback and callback(callback_arg):
            if ctx.unsafe_method and not ctx.idempotent:
                # The server answered, so it executed this POST/PATCH - a retry would repeat it
                self.logger.warning(
                    f"should_retry_callback asked to retry {ctx.method} (status {status_code}); "
                    f"not retrying a non-idempotent request (send an Idempotency-Key header, "
                    f"auto_idempotency_key=True or retry_non_idempotent=True to allow it)")
            else:
                if ctx.unsafe_method:
                    self._mark_possibly_processed(ctx, key)
                self._record(key, endpoint, False, request_time)
                self.logger.warning(
                    f"Retry requested by should_retry_callback (status {status_code}). "
                    f"Attempt {ctx.attempt + 1}/{policy.max_retries}")
                return Action.RETRY, None

        self._record(key, endpoint, True, request_time)
        if not self.pool.auth_confirmed:
            self._confirm_auth(ctx)
        self.limiter.on_success(ctx.reports, key, headers)
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Success (status %s)", status_code)
        return Action.RETURN, None

    def _mark_possibly_processed(self, ctx: RequestContext, key: str) -> None:
        ctx.possibly_processed = True
        if ctx.pinned_key is None:
            ctx.pinned_key = key

    def _select(self, ctx: RequestContext) -> str:
        pinned = ctx.pinned_key
        if pinned is not None and pinned in self.pool.metrics_view():
            return pinned
        key = self.pool.select()
        rejected = ctx.rejected
        if rejected and key in rejected:
            key = self.pool.first_other(rejected) or key
        return key

    def _remove_invalid(self, ctx: RequestContext, key: str, status_code: int) -> None:
        self.logger.error(
            f"Key {mask_key(key)} permanently invalid (status {status_code}); removing it from rotation")
        self.state.report_invalid(ctx.reports, key)
        self.pool.remove(key)

    def _confirm_auth(self, ctx: RequestContext) -> None:
        """The API accepted a request: keys rejected earlier are really invalid."""
        for key, status in self.pool.confirm_auth().items():
            self._remove_invalid(ctx, key, status)

    def _auth_error(self, ctx: RequestContext) -> AuthenticationError:
        rejected = ctx.rejected or {}
        labels = unique_labels(rejected)
        statuses = {labels[k]: status for k, status in rejected.items()}
        builder = self.builder
        sample = next(iter(rejected), None)
        header = builder.masked_auth_header(sample) if sample is not None else None
        if builder.header_callback is not None:
            sent = "the headers returned by header_callback"
        elif header is None:
            sent = "no auth header (auth=False)"
        else:
            sent = f"'{header}'"
        codes = ", ".join(sorted({str(s) for s in statuses.values()}))
        message = (
            f"All {len(rejected)} key(s) were rejected ({codes}) and no request has succeeded yet. "
            f"This usually means the API expects a different auth header, so the keys were kept. "
            f"Sent: {sent}. Set auth='bearer', auth='x-api-key', "
            f"auth=('Header-Name', 'Scheme {{key}}') or header_callback=."
        )
        self.logger.error(message)
        return AuthenticationError(
            message, statuses=statuses,
            auth_header=header if builder.header_callback is None else None,
            last_response=ctx.last_response, last_exception=ctx.last_exception,
        )

    def _record_network_error(self, ctx: RequestContext, key: str, error: BaseException,
                              request_time: float, safe_to_retry: bool) -> bool:
        """Records a network failure. Returns True if the request may be retried."""
        ctx.last_exception = error
        self._record(key, ctx.endpoint, False, request_time)
        ctx.breaker_verdict(False)
        if not ctx.idempotent and not safe_to_retry:
            self.logger.warning(
                f"{ctx.method} failed with {type(error).__name__} after the request may have "
                f"been sent; not retrying a non-idempotent request")
            return False
        if ctx.unsafe_method and not safe_to_retry:
            self._mark_possibly_processed(ctx, key)
        ctx.attempt += 1
        self.logger.warning(
            f"Network error: {type(error).__name__}: {error}. Attempt {ctx.attempt}/{self.policy.max_retries}")
        return True

    def _retry_delay(self, ctx: RequestContext, error_type: ErrorType | None, headers: Any) -> float:
        """
        How long to wait before the next attempt.

        - Rate limit: switch to another available key immediately; if every key
          is rate limited, wait until the earliest one frees up (bounded by max_delay).
        - Temporary server error: honour Retry-After, else exponential backoff.
        - Network error / other: exponential backoff.
        """
        policy = self.policy
        backoff = policy.backoff(ctx.attempt - 1)
        if error_type == ErrorType.RATE_LIMIT:
            pinned = ctx.pinned_key
            if pinned is not None:  # must wait for this very key
                metrics = self.pool.metrics_view().get(pinned)
                if metrics is not None:
                    return min(max(metrics.rate_limit_reset - time.time(), 0.0), policy.max_delay)
            return self.limiter.wait_after_rate_limit(backoff)
        if error_type == ErrorType.TEMPORARY:
            retry_after = parse_retry_after(headers)
            if retry_after is not None:
                return min(retry_after, policy.max_delay)
        return backoff

    def exhausted_error(self, last_response: Any, last_exception: BaseException | None) -> AllKeysExhaustedError:
        max_retries = self.policy.max_retries
        self.logger.error(f"All {max_retries} retries exhausted")
        details = ""
        if last_exception is not None:
            details = f" Last error: {type(last_exception).__name__}: {last_exception}"
        elif last_response is not None:
            status = getattr(last_response, 'status_code', getattr(last_response, 'status', None))
            details = f" Last status: {status}"
        return AllKeysExhaustedError(
            f"All keys exhausted after {max_retries} attempts.{details}",
            last_response=last_response,
            last_exception=last_exception,
        )
