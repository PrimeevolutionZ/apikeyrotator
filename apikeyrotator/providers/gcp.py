"""Secret provider from Google Cloud Secret Manager"""

import json
import logging
import asyncio
from typing import List, Optional


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
        logger: Optional[logging.Logger] = None
    ):
        self.project_id = project_id
        self.secret_id = secret_id
        self.version_id = version_id
        self._client = None
        self.logger = logger if logger else logging.getLogger(__name__)

    async def _get_client(self):
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

    async def get_keys(self) -> List[str]:
        from ..utils import retry_with_backoff

        def _get_secret_value():
            # Note: using sync version for retry_with_backoff
            try:
                from google.cloud import secretmanager
                if self._client is None:
                    self._client = secretmanager.SecretManagerServiceClient()
                client = self._client

                name = f"projects/{self.project_id}/secrets/{self.secret_id}/versions/{self.version_id}"
                response = client.access_secret_version(request={"name": name})
                secret_string = response.payload.data.decode('UTF-8')

                # Parsing similar to AWS
                try:
                    keys_data = json.loads(secret_string)
                    if isinstance(keys_data, list):
                        return [str(k).strip() for k in keys_data if str(k).strip()]
                    elif isinstance(keys_data, str):
                        return [k.strip() for k in keys_data.split(',') if k.strip()]
                except json.JSONDecodeError:
                    return [k.strip() for k in secret_string.split(',') if k.strip()]

                return []

            except Exception as e:

                self.logger.error(f"Error retrieving secret from GCP: {e}")
                return []

        try:
            # Run sync GCP call in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, retry_with_backoff, _get_secret_value, 3, 1.0, Exception)
        except Exception as e:
            self.logger.error(f"Failed to get keys after retries: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()
