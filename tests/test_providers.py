"""
Tests for secret providers
Tests: environment, file, AWS, GCP providers
"""

import pytest
import os
import sys
import json
import tempfile
import builtins
from unittest.mock import Mock, patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apikeyrotator.providers import (
    EnvironmentSecretProvider,
    FileSecretProvider,
    AWSSecretsManagerProvider,
    GCPSecretManagerProvider,
    create_secret_provider,
)

# ... [OTHER PROVIDER TESTS OMITTED - THEY PASSED] ...
# Вставляю только исправленный класс TestAWSSecretsManagerProvider и окружение

class TestAWSSecretsManagerProvider:
    """Test AWS Secrets Manager provider."""

    @pytest.mark.asyncio
    async def test_get_keys_json_array(self):
        mock_response = {'SecretString': '["key1", "key2", "key3"]'}
        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.return_value = mock_response
            mock_boto.return_value = mock_client
            provider = AWSSecretsManagerProvider(secret_name='my-secret', region_name='us-east-1')
            keys = await provider.get_keys()
            assert keys == ['key1', 'key2', 'key3']

    # ... [other tests in this class passed] ...

    @pytest.mark.asyncio
    async def test_get_keys_secret_not_found(self):
        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.side_effect = Exception('ResourceNotFoundException')
            mock_client.exceptions.ResourceNotFoundException = Exception
            mock_boto.return_value = mock_client
            provider = AWSSecretsManagerProvider(secret_name='nonexistent')
            keys = await provider.get_keys()
            assert keys == []

    @pytest.mark.asyncio
    async def test_refresh_keys(self):
        mock_response = {'SecretString': '["key1", "key2"]'}
        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.return_value = mock_response
            mock_boto.return_value = mock_client
            provider = AWSSecretsManagerProvider(secret_name='my-secret')
            keys = await provider.refresh_keys()
            assert keys == ['key1', 'key2']

    @pytest.mark.asyncio
    async def test_boto3_not_installed(self):
        """Test error when boto3 is not installed."""
        provider = AWSSecretsManagerProvider(secret_name='my-secret')
        provider._client = None

        # Исправление: используем patch.dict для sys.modules, чтобы симулировать отсутствие модуля
        # вместо патчинга встроенного __import__, который вызывает рекурсию
        with patch.dict('sys.modules', {'boto3': None}):
            with pytest.raises(ImportError, match='boto3 is not installed'):
                await provider._get_client()

# ... [GCP Tests and Factory Tests passed] ...