import logging
import inspect
from typing import List, Optional, Callable, Any, Dict, Tuple, Union

from .core.rotator import BaseKeyRotator, APIKeyRotator, AsyncAPIKeyRotator
from .core.exceptions import AllKeysExhaustedError, AllProvidersExhaustedError

class ProviderRoute:
    """
    A route definition for a specific service provider.
    """
    def __init__(
        self,
        rotator: BaseKeyRotator,
        name: str = "default",
        request_transformer: Optional[Callable[[str, str, Dict[str, Any]], Tuple[str, str, Dict[str, Any]]]] = None,
        condition: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None,
        on_exhausted: Optional[Callable[[], Any]] = None
    ):
        """
        Args:
            rotator: Instance of APIKeyRotator or AsyncAPIKeyRotator.
            name: Logical name for this provider.
            request_transformer: A callable that takes (method, url, kwargs) and returns a modified (method, url, kwargs)
                                 suited for this specific provider.
            condition: A callable that returns True if this route is applicable for the current request.
            on_exhausted: A callback executed when all keys for this specific provider are exhausted.
        """
        self.rotator = rotator
        self.name = name
        self.request_transformer = request_transformer
        self.condition = condition
        self.on_exhausted = on_exhausted


class FallbackRouter:
    """
    Manages multiple providers and automatically falls back to the next one
    if the current one exhausts all its keys.
    """
    def __init__(
        self,
        routes: List[ProviderRoute],
        on_all_exhausted: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            routes: List of ProviderRoutes to attempt in order.
            on_all_exhausted: A callback executed when all providers fail. Can return a mock response.
            logger: Optional logger instance.
        """
        self.routes = routes
        self.on_all_exhausted = on_all_exhausted
        self.logger = logger or logging.getLogger(__name__)

    def request(self, method: str, url: str, **kwargs) -> Any:
        """
        Execute a synchronous request, falling back through routes as needed.
        """
        for route in self.routes:
            if route.condition and not route.condition(method, url, kwargs):
                self.logger.debug(f"Skipping route '{route.name}' (condition not met)")
                continue

            req_method, req_url, req_kwargs = method, url, kwargs
            if route.request_transformer:
                req_method, req_url, req_kwargs = route.request_transformer(method, url, kwargs)

            if not isinstance(route.rotator, APIKeyRotator):
                self.logger.warning(f"Route '{route.name}' has async rotator but used in sync request()")
                continue

            try:
                self.logger.info(f"Routing request to provider: {route.name}")
                return route.rotator.request(req_method, req_url, **req_kwargs)
            except AllKeysExhaustedError:
                self.logger.warning(f"Provider '{route.name}' exhausted all keys. Moving to next route.")
                if route.on_exhausted:
                    route.on_exhausted()
                continue

        if self.on_all_exhausted:
            self.logger.warning("All providers exhausted. Executing fallback action.")
            return self.on_all_exhausted(method, url, kwargs)

        raise AllProvidersExhaustedError("All configured providers and their keys are exhausted.")

    def get(self, url: str, **kwargs) -> Any:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Any:
        return self.request("POST", url, **kwargs)

    async def request_async(self, method: str, url: str, **kwargs) -> Any:
        """
        Execute an asynchronous request, falling back through routes as needed.
        """
        for route in self.routes:
            if route.condition and not route.condition(method, url, kwargs):
                self.logger.debug(f"Skipping route '{route.name}' (condition not met)")
                continue

            req_method, req_url, req_kwargs = method, url, kwargs
            if route.request_transformer:
                req_method, req_url, req_kwargs = route.request_transformer(method, url, kwargs)

            if not isinstance(route.rotator, AsyncAPIKeyRotator):
                self.logger.warning(f"Route '{route.name}' has sync rotator but used in async request_async()")
                continue

            try:
                self.logger.info(f"Routing async request to provider: {route.name}")
                return await route.rotator.request_async(req_method, req_url, **req_kwargs)
            except AllKeysExhaustedError:
                self.logger.warning(f"Provider '{route.name}' exhausted all keys. Moving to next route.")
                if route.on_exhausted:
                    if inspect.iscoroutinefunction(route.on_exhausted):
                        await route.on_exhausted()
                    else:
                        route.on_exhausted()
                continue

        if self.on_all_exhausted:
            self.logger.warning("All providers exhausted. Executing fallback action.")
            if inspect.iscoroutinefunction(self.on_all_exhausted):
                return await self.on_all_exhausted(method, url, kwargs)
            return self.on_all_exhausted(method, url, kwargs)

        raise AllProvidersExhaustedError("All configured providers and their keys are exhausted.")

    async def get_async(self, url: str, **kwargs) -> Any:
        return await self.request_async("GET", url, **kwargs)

    async def post_async(self, url: str, **kwargs) -> Any:
        return await self.request_async("POST", url, **kwargs)
