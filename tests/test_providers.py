"""
Tests for secret providers
Tests: environment, file, AWS, GCP providers
"""

import pytest
import os
import sys
import json
import tempfile
from unittest.mock import Mock, patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apikeyrotator.providers import (
    EnvironmentSecretProvider,
    FileSecretProvider,
    AWSSecretsManagerProvider,
    GCPSecretManagerProvider,
    create_secret_provider,
)


# ============================================================================
# ENVIRONMENT PROVIDER TESTS
# ============================================================================

class TestEnvironmentSecretProvider:
    """Test environment variable secret provider."""

    @pytest.mark.asyncio
    async def test_get_keys_from_env(self, monkeypatch):
        """Test loading keys from environment variable."""
        monkeypatch.setenv('API_KEYS', 'key1,key2,key3')

        provider = EnvironmentSecretProvider(env_var='API_KEYS')
        keys = await provider.get_keys()

        assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_empty_env(self, monkeypatch):
        """Test behavior when environment variable is not set."""
        monkeypatch.delenv('API_KEYS', raising=False)

        provider = EnvironmentSecretProvider(env_var='API_KEYS')
        keys = await provider.get_keys()

        assert keys == []

    @pytest.mark.asyncio
    async def test_get_keys_with_spaces(self, monkeypatch):
        """Test trimming whitespace from keys."""
        monkeypatch.setenv('API_KEYS', ' key1 , key2 , key3 ')

        provider = EnvironmentSecretProvider()
        keys = await provider.get_keys()

        assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_empty_values(self, monkeypatch):
        """Test filtering out empty keys."""
        monkeypatch.setenv('API_KEYS', 'key1,,key2,  ,key3')

        provider = EnvironmentSecretProvider()
        keys = await provider.get_keys()

        assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_refresh_keys(self, monkeypatch):
        """Test refreshing keys returns updated values."""
        monkeypatch.setenv('API_KEYS', 'key1,key2')

        provider = EnvironmentSecretProvider()
        keys1 = await provider.get_keys()

        monkeypatch.setenv('API_KEYS', 'key3,key4')
        keys2 = await provider.refresh_keys()

        assert keys1 == ['key1', 'key2']
        assert keys2 == ['key3', 'key4']

    @pytest.mark.asyncio
    async def test_custom_env_var(self, monkeypatch):
        """Test using custom environment variable name."""
        monkeypatch.setenv('MY_CUSTOM_KEYS', 'keyA,keyB')

        provider = EnvironmentSecretProvider(env_var='MY_CUSTOM_KEYS')
        keys = await provider.get_keys()

        assert keys == ['keyA', 'keyB']


# ============================================================================
# FILE PROVIDER TESTS
# ============================================================================

class TestFileSecretProvider:
    """Test file-based secret provider."""

    @pytest.mark.asyncio
    async def test_get_keys_from_json_array(self):
        """Test loading keys from JSON array file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(['key1', 'key2', 'key3'], f)
            temp_path = f.name

        try:
            provider = FileSecretProvider(file_path=temp_path)
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_get_keys_from_csv(self):
        """Test loading keys from CSV format."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('key1,key2,key3')
            temp_path = f.name

        try:
            provider = FileSecretProvider(file_path=temp_path)
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_get_keys_from_lines(self):
        """Test loading keys one per line."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('key1\nkey2\nkey3')
            temp_path = f.name

        try:
            provider = FileSecretProvider(file_path=temp_path)
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_get_keys_nonexistent_file(self):
        """Test behavior when file doesn't exist."""
        provider = FileSecretProvider(file_path='/nonexistent/path/keys.txt')
        keys = await provider.get_keys()

        assert keys == []

    @pytest.mark.asyncio
    async def test_get_keys_empty_file(self):
        """Test loading from empty file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_path = f.name

        try:
            provider = FileSecretProvider(file_path=temp_path)
            keys = await provider.get_keys()

            assert keys == []
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_get_keys_with_blank_lines(self):
        """Test filtering blank lines."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('key1\n\nkey2\n  \nkey3\n')
            temp_path = f.name

        try:
            provider = FileSecretProvider(file_path=temp_path)
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_refresh_keys(self):
        """Test refreshing keys from file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('key1,key2')
            temp_path = f.name

        try:
            provider = FileSecretProvider(file_path=temp_path)
            keys1 = await provider.get_keys()

            # Update file
            with open(temp_path, 'w') as f2:
                f2.write('key3,key4,key5')

            keys2 = await provider.refresh_keys()

            assert keys1 == ['key1', 'key2']
            assert keys2 == ['key3', 'key4', 'key5']
        finally:
            os.unlink(temp_path)


# ============================================================================
# AWS SECRETS MANAGER PROVIDER TESTS
# ============================================================================

class TestAWSSecretsManagerProvider:
    """Test AWS Secrets Manager provider."""

    @pytest.mark.asyncio
    async def test_get_keys_json_array(self):
        """Test loading keys from JSON array format."""
        mock_response = {
            'SecretString': '["key1", "key2", "key3"]'
        }

        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.return_value = mock_response
            mock_boto.return_value = mock_client

            provider = AWSSecretsManagerProvider(
                secret_name='my-secret',
                region_name='us-east-1'
            )
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_json_object_with_keys(self):
        """Test loading from JSON object with 'keys' field."""
        mock_response = {
            'SecretString': '{"keys": ["key1", "key2"]}'
        }

        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.return_value = mock_response
            mock_boto.return_value = mock_client

            provider = AWSSecretsManagerProvider(secret_name='my-secret')
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2']

    @pytest.mark.asyncio
    async def test_get_keys_json_object_with_api_keys(self):
        """Test loading from JSON object with 'api_keys' field."""
        mock_response = {
            'SecretString': '{"api_keys": ["keyA", "keyB", "keyC"]}'
        }

        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.return_value = mock_response
            mock_boto.return_value = mock_client

            provider = AWSSecretsManagerProvider(secret_name='my-secret')
            keys = await provider.get_keys()

            assert keys == ['keyA', 'keyB', 'keyC']

    @pytest.mark.asyncio
    async def test_get_keys_csv_string(self):
        """Test loading from CSV string."""
        mock_response = {
            'SecretString': 'key1,key2,key3'
        }

        with patch('boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_secret_value.return_value = mock_response
            mock_boto.return_value = mock_client

            provider = AWSSecretsManagerProvider(secret_name='my-secret')
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_secret_not_found(self):
        """Test handling of non-existent secret."""
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
        """Test refreshing keys from AWS."""
        mock_response = {
            'SecretString': '["key1", "key2"]'
        }

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
        provider._client = None  # Reset client

        # Patch the import statement inside _get_client
        def mock_import(name, *args, **kwargs):
            if name == 'boto3':
                raise ImportError("No module named 'boto3'")
            return __import__(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with pytest.raises(ImportError, match='boto3 is not installed'):
                await provider.get_keys()


# ============================================================================
# GCP SECRET MANAGER PROVIDER TESTS
# ============================================================================

class TestGCPSecretManagerProvider:
    """Test GCP Secret Manager provider."""

    @pytest.mark.asyncio
    async def test_get_keys_json_array(self):
        """Test loading keys from JSON array."""
        # Create a proper mock structure
        from unittest.mock import MagicMock

        mock_payload = MagicMock()
        mock_payload.data = b'["key1", "key2", "key3"]'
        mock_response = MagicMock()
        mock_response.payload = mock_payload

        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = mock_response

        mock_secret_manager = MagicMock()
        mock_secret_manager.SecretManagerServiceClient.return_value = mock_client

        # Create mock google modules
        mock_google = MagicMock()
        mock_google_cloud = MagicMock()
        mock_google.cloud = mock_google_cloud
        mock_google_cloud.secretmanager = mock_secret_manager

        with patch.dict('sys.modules', {
            'google': mock_google,
            'google.cloud': mock_google_cloud,
            'google.cloud.secretmanager': mock_secret_manager
        }):
            provider = GCPSecretManagerProvider(
                project_id='my-project',
                secret_id='my-secret'
            )
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_csv_string(self):
        """Test loading keys from CSV string."""
        from unittest.mock import MagicMock

        mock_payload = MagicMock()
        mock_payload.data = b'key1,key2,key3'
        mock_response = MagicMock()
        mock_response.payload = mock_payload

        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = mock_response

        mock_secret_manager = MagicMock()
        mock_secret_manager.SecretManagerServiceClient.return_value = mock_client

        mock_google = MagicMock()
        mock_google_cloud = MagicMock()
        mock_google.cloud = mock_google_cloud
        mock_google_cloud.secretmanager = mock_secret_manager

        with patch.dict('sys.modules', {
            'google': mock_google,
            'google.cloud': mock_google_cloud,
            'google.cloud.secretmanager': mock_secret_manager
        }):
            provider = GCPSecretManagerProvider(
                project_id='my-project',
                secret_id='my-secret'
            )
            keys = await provider.get_keys()

            assert keys == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_with_version(self):
        """Test loading specific version."""
        from unittest.mock import MagicMock

        mock_payload = MagicMock()
        mock_payload.data = b'["keyA", "keyB"]'
        mock_response = MagicMock()
        mock_response.payload = mock_payload

        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = mock_response

        mock_secret_manager = MagicMock()
        mock_secret_manager.SecretManagerServiceClient.return_value = mock_client

        mock_google = MagicMock()
        mock_google_cloud = MagicMock()
        mock_google.cloud = mock_google_cloud
        mock_google_cloud.secretmanager = mock_secret_manager

        with patch.dict('sys.modules', {
            'google': mock_google,
            'google.cloud': mock_google_cloud,
            'google.cloud.secretmanager': mock_secret_manager
        }):
            provider = GCPSecretManagerProvider(
                project_id='my-project',
                secret_id='my-secret',
                version_id='2'
            )
            keys = await provider.get_keys()

            assert keys == ['keyA', 'keyB']
            # Verify correct version was requested
            call_args = mock_client.access_secret_version.call_args
            assert 'versions/2' in call_args[1]['request']['name']

    @pytest.mark.asyncio
    async def test_get_keys_error_handling(self):
        """Test error handling."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = Exception('Permission denied')

        mock_secret_manager = MagicMock()
        mock_secret_manager.SecretManagerServiceClient.return_value = mock_client

        mock_google = MagicMock()
        mock_google_cloud = MagicMock()
        mock_google.cloud = mock_google_cloud
        mock_google_cloud.secretmanager = mock_secret_manager

        with patch.dict('sys.modules', {
            'google': mock_google,
            'google.cloud': mock_google_cloud,
            'google.cloud.secretmanager': mock_secret_manager
        }):
            provider = GCPSecretManagerProvider(
                project_id='my-project',
                secret_id='my-secret'
            )
            keys = await provider.get_keys()

            assert keys == []

    @pytest.mark.asyncio
    async def test_refresh_keys(self):
        """Test refreshing keys."""
        from unittest.mock import MagicMock

        mock_payload = MagicMock()
        mock_payload.data = b'["key1", "key2"]'
        mock_response = MagicMock()
        mock_response.payload = mock_payload

        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = mock_response

        mock_secret_manager = MagicMock()
        mock_secret_manager.SecretManagerServiceClient.return_value = mock_client

        mock_google = MagicMock()
        mock_google_cloud = MagicMock()
        mock_google.cloud = mock_google_cloud
        mock_google_cloud.secretmanager = mock_secret_manager

        with patch.dict('sys.modules', {
            'google': mock_google,
            'google.cloud': mock_google_cloud,
            'google.cloud.secretmanager': mock_secret_manager
        }):
            provider = GCPSecretManagerProvider(
                project_id='my-project',
                secret_id='my-secret'
            )
            keys = await provider.refresh_keys()

            assert keys == ['key1', 'key2']


# ============================================================================
# FACTORY TESTS
# ============================================================================

class TestSecretProviderFactory:
    """Test secret provider factory."""

    def test_create_environment_provider(self):
        """Test creating environment provider."""
        provider = create_secret_provider('env', env_var='MY_KEYS')

        assert isinstance(provider, EnvironmentSecretProvider)
        assert provider.env_var == 'MY_KEYS'

    def test_create_environment_provider_alias(self):
        """Test 'environment' alias."""
        provider = create_secret_provider('environment', env_var='API_KEYS')

        assert isinstance(provider, EnvironmentSecretProvider)

    def test_create_file_provider(self):
        """Test creating file provider."""
        provider = create_secret_provider('file', file_path='/path/to/keys.txt')

        assert isinstance(provider, FileSecretProvider)
        assert provider.file_path == '/path/to/keys.txt'

    def test_create_aws_provider(self):
        """Test creating AWS provider."""
        provider = create_secret_provider(
            'aws_secrets_manager',
            secret_name='my-secret',
            region_name='us-west-2'
        )

        assert isinstance(provider, AWSSecretsManagerProvider)
        assert provider.secret_name == 'my-secret'
        assert provider.region_name == 'us-west-2'

    def test_create_aws_provider_alias(self):
        """Test 'aws' alias."""
        provider = create_secret_provider('aws', secret_name='test')

        assert isinstance(provider, AWSSecretsManagerProvider)

    def test_create_gcp_provider(self):
        """Test creating GCP provider."""
        provider = create_secret_provider(
            'gcp_secret_manager',
            project_id='my-project',
            secret_id='my-secret'
        )

        assert isinstance(provider, GCPSecretManagerProvider)
        assert provider.project_id == 'my-project'
        assert provider.secret_id == 'my-secret'

    def test_create_gcp_provider_alias(self):
        """Test 'gcp' alias."""
        provider = create_secret_provider(
            'gcp',
            project_id='test-project',
            secret_id='test-secret'
        )

        assert isinstance(provider, GCPSecretManagerProvider)

    def test_unknown_provider_type(self):
        """Test error on unknown provider type."""
        with pytest.raises(ValueError, match='Unknown secret provider type'):
            create_secret_provider('unknown_provider')

    def test_case_insensitive_provider_type(self):
        """Test factory handles case-insensitive types."""
        provider1 = create_secret_provider('ENV', env_var='KEYS')
        provider2 = create_secret_provider('File', file_path='/path')

        assert isinstance(provider1, EnvironmentSecretProvider)
        assert isinstance(provider2, FileSecretProvider)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])