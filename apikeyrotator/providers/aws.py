"""Secret provider for AWS Secrets Manager"""

import logging
import asyncio
from typing import List, Optional

from .base import parse_secret_payload


class AWSSecretsManagerProvider:
    """
    Secret provider from AWS Secrets Manager.

    Requires: pip install boto3

    Secret can be in formats:
    - JSON array: ["key1", "key2"]
    - JSON object: {"keys": ["key1", "key2"]} or {"api_keys": ["key1", "key2"]}
    - JSON string: "key1,key2,key3"
    - Plain string: key1,key2,key3
    """

    def __init__(
        self,
        secret_name: str,
        region_name: str = 'us-east-1',
        logger: Optional[logging.Logger] = None
    ):
        self.secret_name = secret_name
        self.region_name = region_name
        self._client = None
        self.logger = logger if logger else logging.getLogger(__name__)

    def _get_client(self):
        """Creates or returns boto3 client"""
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is not installed. "
                "Install it with: pip install boto3"
            )

        if self._client is None:
            self._client = boto3.client(
                'secretsmanager',
                region_name=self.region_name
            )
        return self._client

    async def get_keys(self) -> List[str]:
        from ..utils import retry_with_backoff

        def _get_secret_value() -> List[str]:
            client = self._get_client()
            try:
                response = client.get_secret_value(SecretId=self.secret_name)
            except client.exceptions.ResourceNotFoundException:
                # Not retryable
                self.logger.error(f"Secret {self.secret_name} not found in AWS Secrets Manager")
                return []
            # Other errors propagate so retry_with_backoff can retry them

            secret = response.get('SecretString')
            if secret is None:
                return []
            return parse_secret_payload(secret)

        # Fail fast (without retries) if the SDK is not installed
        self._get_client()

        try:
            # Run sync boto3 call in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, retry_with_backoff, _get_secret_value, 3, 1.0, Exception)
        except Exception as e:
            self.logger.error(f"Failed to get keys from AWS secret {self.secret_name} after retries: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()
