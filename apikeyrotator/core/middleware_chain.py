"""Runs middleware hooks in list order (sync `*_sync` hooks or awaited async hooks)."""

from __future__ import annotations
import logging
import warnings
from typing import Any

from apikeyrotator.middleware import ErrorInfo, RequestInfo, ResponseInfo, RotatorMiddleware


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


_HOOKS = (("before_request", "before_request_sync"),
          ("after_request", "after_request_sync"),
          ("on_error", "on_error_sync"))


def _overrides(middleware: Any, name: str) -> bool:
    """True if the middleware implements `name` itself (not the RotatorMiddleware default)."""
    impl = getattr(type(middleware), name, None)
    if impl is None:
        return False
    return impl is not getattr(RotatorMiddleware, name, None)


def _async_hook(middleware: Any, name: str, sync_name: str) -> Any:
    """The async hook, or the sync one for middlewares that only implement sync hooks."""
    hook = getattr(middleware, name, None)
    return hook if hook is not None else getattr(middleware, sync_name, None)


def _apply_request_info(request_info: RequestInfo, request_kwargs: dict[str, Any]) -> None:
    request_kwargs["headers"] = request_info.headers
    request_kwargs["cookies"] = request_info.cookies


class MiddlewareChain:
    """
    before_request: a RequestInfo result replaces the request (headers/cookies),
    a ResponseInfo result short-circuits it (e.g. cache hit).
    on_error: failures of a hook are logged, never break the retry loop.
    """

    __slots__ = ('middlewares', 'logger')

    def __init__(self, middlewares: list[RotatorMiddleware] | None, logger: logging.Logger):
        self.middlewares: list[RotatorMiddleware] = middlewares if middlewares is not None else []
        self.logger = logger

    def warn_async_only(self) -> None:
        """Warns about middlewares whose hooks a sync rotator would never call."""
        for middleware in self.middlewares:
            missing = [
                name for name, sync_name in _HOOKS
                if _overrides(middleware, name) and not _overrides(middleware, sync_name)
            ]
            if missing:
                name = type(middleware).__name__
                message = (
                    f"{name} implements only async hooks ({', '.join(missing)}); APIKeyRotator "
                    f"calls the *_sync hooks, so they will never run. Implement "
                    f"{', '.join(m + '_sync' for m in missing)} or use AsyncAPIKeyRotator."
                )
                warnings.warn(message, UserWarning, stacklevel=4)
                self.logger.warning(message)

    # --- sync ---

    def before_sync(self, request_info: RequestInfo, request_kwargs: dict[str, Any]) -> ResponseInfo | None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'before_request_sync', None)
            if hook is None:
                continue
            result = hook(request_info)
            if isinstance(result, ResponseInfo):
                return result
            if isinstance(result, RequestInfo):
                request_info = result
                _apply_request_info(request_info, request_kwargs)
        return None

    def after_sync(self, response_info: ResponseInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'after_request_sync', None)
            if hook is not None:
                result = hook(response_info)
                if isinstance(result, ResponseInfo):
                    response_info = result

    def on_error_sync(self, error_info: ErrorInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'on_error_sync', None)
            if hook is None:
                continue
            try:
                hook(error_info)
            except Exception as e:
                self.logger.warning(f"Middleware {type(middleware).__name__}.on_error_sync failed: {e}")

    # --- async ---

    async def before(self, request_info: RequestInfo, request_kwargs: dict[str, Any]) -> ResponseInfo | None:
        for middleware in self.middlewares:
            hook = _async_hook(middleware, 'before_request', 'before_request_sync')
            if hook is None:
                continue
            result = await _maybe_await(hook(request_info))
            if isinstance(result, ResponseInfo):
                return result
            if isinstance(result, RequestInfo):
                request_info = result
                _apply_request_info(request_info, request_kwargs)
        return None

    async def after(self, response_info: ResponseInfo) -> None:
        for middleware in self.middlewares:
            hook = _async_hook(middleware, 'after_request', 'after_request_sync')
            if hook is not None:
                result = await _maybe_await(hook(response_info))
                if isinstance(result, ResponseInfo):
                    response_info = result

    async def on_error(self, error_info: ErrorInfo) -> None:
        for middleware in self.middlewares:
            hook = _async_hook(middleware, 'on_error', 'on_error_sync')
            if hook is None:
                continue
            try:
                await _maybe_await(hook(error_info))
            except Exception as e:
                self.logger.warning(f"Middleware {type(middleware).__name__}.on_error failed: {e}")
