"""Secret provider for AWS Secrets Manager"""

import json
import logging
import asyncio
from typing import List, Optional


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

        def _get_secret_value():
            client = self._get_client()
            try:
                response = client.get_secret_value(SecretId=self.secret_name)

                if 'SecretString' in response:
                    secret = response['SecretString']

                    # Try parsing as JSON
                    try:
                        keys_data = json.loads(secret)

                        if isinstance(keys_data, list):
                            return [str(k).strip() for k in keys_data if str(k).strip()]
                        elif isinstance(keys_data, dict):
                            # Extract from 'keys' or 'api_keys'
                            keys_list = keys_data.get('keys') or keys_data.get('api_keys')

                            if keys_list is None:
                                keys_list = list(keys_data.values())

                            if isinstance(keys_list, list):
                                return [str(k).strip() for k in keys_list if str(k).strip()]
                            elif isinstance(keys_list, str):
                                return [k.strip() for k in keys_list.split(',') if k.strip()]
                        elif isinstance(keys_data, str):
                            return [k.strip() for k in keys_data.split(',') if k.strip()]

                    except json.JSONDecodeError:
                        # Not JSON - parse as CSV
                        return [k.strip() for k in secret.split(',') if k.strip()]

                return []

            except client.exceptions.ResourceNotFoundException:
                self.logger.error(f"Secret {self.secret_name} not found in AWS Secrets Manager")
                return []
            except Exception as e:
                self.logger.error(f"Error retrieving secret {self.secret_name}: {e}")
                return []

        try:
            # Run sync boto3 call in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, retry_with_backoff, _get_secret_value, 3, 1.0, Exception)
        except Exception as e:
            self.logger.error(f"Failed to get keys after retries: {e}")
            return []

    async def refresh_keys(self) -> List[str]:
        return await self.get_keys()
