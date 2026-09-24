"""Secret provider from Google Cloud Secret Manager"""

import asyncio
import logging

from .base import parse_secret_payload


class GCPSecretManagerProvider:
    """
    Secret provider from GCP Secret Manager.

    Requires: pip install google-cloud-secret-manager
    """

    def __init__(
        self,
        project_id: str,
        secret_id: str,
        version_id: str = "latest",
        logger: logging.Logger | None = None
    ):
        self.project_id = project_id
        self.secret_id = secret_id
        self.version_id = version_id
        self._client = None
        self.logger = logger if logger else logging.getLogger(__name__)

    def _get_client(self):
        """Creates or returns GCP client"""
        try:
            from google.cloud import secretmanager
        except ImportError:
            raise ImportError(
                "google-cloud-secret-manager is not installed. "
                "Install it with: pip install google-cloud-secret-manager"
            )

        if self._client is None:
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    async def get_keys(self) -> list[str]:
        from ..utils import retry_with_backoff

        def _get_secret_value() -> list[str]:
            client = self._get_client()
            name = f"projects/{self.project_id}/secrets/{self.secret_id}/versions/{self.version_id}"
            # Errors propagate so retry_with_backoff can retry them
            response = client.access_secret_version(request={"name": name})
            return parse_secret_payload(response.payload.data.decode('UTF-8'))

        # Fail fast (without retries) if the SDK is not installed
        self._get_client()

        try:
            # Run sync GCP call in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, retry_with_backoff, _get_secret_value, 3, 1.0, Exception)
        except Exception as e:
            self.logger.error(f"Failed to get keys from GCP secret {self.secret_id} after retries: {e}")
            return []

    async def refresh_keys(self) -> list[str]:
        return await self.get_keys()
