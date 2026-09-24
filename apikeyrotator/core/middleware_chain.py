"""Runs middleware hooks in list order (sync `*_sync` hooks or awaited async hooks)."""

from __future__ import annotations
import logging
from typing import Any

from apikeyrotator.middleware import ErrorInfo, RequestInfo, ResponseInfo, RotatorMiddleware


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


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
            hook = getattr(middleware, 'before_request', None)
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
            hook = getattr(middleware, 'after_request', None)
            if hook is not None:
                result = await _maybe_await(hook(response_info))
                if isinstance(result, ResponseInfo):
                    response_info = result

    async def on_error(self, error_info: ErrorInfo) -> None:
        for middleware in self.middlewares:
            hook = getattr(middleware, 'on_error', None)
            if hook is None:
                continue
            try:
                await _maybe_await(hook(error_info))
            except Exception as e:
                self.logger.warning(f"Middleware {type(middleware).__name__}.on_error failed: {e}")
