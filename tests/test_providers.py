"""
Tests for secret providers
Tests: environment, file, AWS, GCP providers
"""

import pytest
import os
import sys
import json
import types
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apikeyrotator import APIKeyRotator
from apikeyrotator.providers import (
    EnvironmentSecretProvider,
    FileSecretProvider,
    AWSSecretsManagerProvider,
    GCPSecretManagerProvider,
    create_secret_provider,
)
from apikeyrotator.providers.base import parse_secret_payload


def _fake_boto3(client):
    """Builds a stand-in boto3 module so AWS tests don't require boto3."""
    module = types.ModuleType("boto3")
    module.client = Mock(return_value=client)
    return module


def _aws_client(response=None, side_effect=None):
    client = Mock()
    client.exceptions.ResourceNotFoundException = type("ResourceNotFoundException", (Exception,), {})
    if side_effect is not None:
        client.get_secret_value.side_effect = side_effect
    else:
        client.get_secret_value.return_value = response
    return client


class TestParseSecretPayload:
    def test_json_array(self):
        assert parse_secret_payload('["k1", "k2"]') == ['k1', 'k2']

    def test_json_object(self):
        assert parse_secret_payload('{"api_keys": ["k1"]}') == ['k1']
        assert parse_secret_payload('{"a": "k1", "b": "k2"}') == ['k1', 'k2']

    def test_csv_and_newlines(self):
        assert parse_secret_payload('k1, k2\nk3') == ['k1', 'k2', 'k3']


class TestEnvironmentSecretProvider:
    @pytest.mark.asyncio
    async def test_get_keys(self, monkeypatch):
        monkeypatch.setenv("TEST_KEYS", "k1, k2 ,k3")
        assert await EnvironmentSecretProvider("TEST_KEYS").get_keys() == ['k1', 'k2', 'k3']

    @pytest.mark.asyncio
    async def test_missing_env(self, monkeypatch):
        monkeypatch.delenv("TEST_KEYS", raising=False)
        assert await EnvironmentSecretProvider("TEST_KEYS").get_keys() == []


class TestFileSecretProvider:
    @pytest.mark.asyncio
    async def test_json_file(self, tmp_path):
        path = tmp_path / "keys.json"
        path.write_text(json.dumps(["k1", "k2"]))
        assert await FileSecretProvider(str(path)).get_keys() == ['k1', 'k2']

    @pytest.mark.asyncio
    async def test_lines_file_with_comments(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("# comment\nk1\n\nk2\n")
        assert await FileSecretProvider(str(path)).get_keys() == ['k1', 'k2']

    @pytest.mark.asyncio
    async def test_mixed_csv_and_lines(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("k1,k2\nk3")
        assert await FileSecretProvider(str(path)).get_keys() == ['k1', 'k2', 'k3']

    @pytest.mark.asyncio
    async def test_missing_file(self, tmp_path):
        assert await FileSecretProvider(str(tmp_path / "nope.txt")).get_keys() == []


class TestAWSSecretsManagerProvider:
    """Test AWS Secrets Manager provider."""

    @pytest.mark.asyncio
    async def test_get_keys_json_array(self):
        client = _aws_client({'SecretString': '["key1", "key2", "key3"]'})
        with patch.dict('sys.modules', {'boto3': _fake_boto3(client)}):
            provider = AWSSecretsManagerProvider(secret_name='my-secret', region_name='us-east-1')
            assert await provider.get_keys() == ['key1', 'key2', 'key3']

    @pytest.mark.asyncio
    async def test_get_keys_json_object(self):
        client = _aws_client({'SecretString': '{"keys": ["a", "b"]}'})
        with patch.dict('sys.modules', {'boto3': _fake_boto3(client)}):
            assert await AWSSecretsManagerProvider(secret_name='s').get_keys() == ['a', 'b']

    @pytest.mark.asyncio
    async def test_get_keys_secret_not_found(self):
        client = _aws_client()
        client.get_secret_value.side_effect = client.exceptions.ResourceNotFoundException("nope")
        with patch.dict('sys.modules', {'boto3': _fake_boto3(client)}):
            provider = AWSSecretsManagerProvider(secret_name='nonexistent')
            assert await provider.get_keys() == []
        # Not found is not retried
        assert client.get_secret_value.call_count == 1

    @pytest.mark.asyncio
    async def test_transient_error_is_retried(self):
        client = _aws_client(side_effect=[RuntimeError("throttled"), {'SecretString': 'k1,k2'}])
        with patch.dict('sys.modules', {'boto3': _fake_boto3(client)}), \
                patch('apikeyrotator.utils.retry.time.sleep'):
            provider = AWSSecretsManagerProvider(secret_name='s')
            assert await provider.get_keys() == ['k1', 'k2']
        assert client.get_secret_value.call_count == 2

    @pytest.mark.asyncio
    async def test_refresh_keys(self):
        client = _aws_client({'SecretString': '["key1", "key2"]'})
        with patch.dict('sys.modules', {'boto3': _fake_boto3(client)}):
            provider = AWSSecretsManagerProvider(secret_name='my-secret')
            assert await provider.refresh_keys() == ['key1', 'key2']

    @pytest.mark.asyncio
    async def test_boto3_not_installed(self):
        provider = AWSSecretsManagerProvider(secret_name='my-secret')
        with patch.dict('sys.modules', {'boto3': None}):
            with pytest.raises(ImportError, match='boto3 is not installed'):
                await provider.get_keys()


class TestGCPSecretManagerProvider:
    @pytest.mark.asyncio
    async def test_get_keys(self):
        provider = GCPSecretManagerProvider(project_id='p', secret_id='s')
        client = Mock()
        client.access_secret_version.return_value.payload.data = b'["g1", "g2"]'
        provider._client = client
        with patch.object(GCPSecretManagerProvider, '_get_client', return_value=client):
            assert await provider.get_keys() == ['g1', 'g2']
        name = client.access_secret_version.call_args[1]['request']['name']
        assert name == 'projects/p/secrets/s/versions/latest'


class TestProviderFactory:
    def test_env(self):
        assert isinstance(create_secret_provider('env', env_var='X'), EnvironmentSecretProvider)

    def test_file(self):
        assert isinstance(create_secret_provider('file', file_path='x'), FileSecretProvider)

    def test_aws(self):
        assert isinstance(create_secret_provider('aws', secret_name='x'), AWSSecretsManagerProvider)

    def test_gcp(self):
        assert isinstance(create_secret_provider('gcp', project_id='p', secret_id='s'), GCPSecretManagerProvider)

    def test_unknown(self):
        with pytest.raises(ValueError):
            create_secret_provider('vault')


class TestRotatorWithProvider:
    def test_rotator_loads_keys_from_provider(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("pk1\npk2")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False)
        assert rotator.keys == ['pk1', 'pk2']

    @pytest.mark.asyncio
    async def test_rotator_loads_keys_inside_running_loop(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("pk1")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False)
        assert rotator.keys == ['pk1']

    @pytest.mark.asyncio
    async def test_refresh_preserves_metrics(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("pk1\npk2")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False)
        rotator._key_metrics['pk1'].update_from_request(success=True, response_time=0.1)

        path.write_text("pk1\npk3")
        keys = await rotator.refresh_keys_from_provider()

        assert keys == ['pk1', 'pk3']
        assert rotator.get_key_statistics()['pk1']['total_requests'] == 1

    def test_refresh_with_empty_result_keeps_keys(self, tmp_path):
        path = tmp_path / "keys.txt"
        path.write_text("pk1")
        rotator = APIKeyRotator(secret_provider=FileSecretProvider(str(path)), load_env_file=False)
        path.write_text("")
        assert rotator.refresh_keys_from_provider_sync() == ['pk1']
