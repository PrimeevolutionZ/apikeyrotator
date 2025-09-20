import pytest
from apikeyrotator import APIKeyRotator, NoAPIKeysError

def test_init_with_list():
    rotator = APIKeyRotator(api_keys=["key1", "key2"])
    assert len(rotator.keys) == 2
    assert rotator.keys == ["key1", "key2"]

def test_init_with_string():
    rotator = APIKeyRotator(api_keys="key1,key2,key3")
    assert len(rotator.keys) == 3
    assert rotator.keys == ["key1", "key2", "key3"]

def test_init_no_keys_raises_error():
    with pytest.raises(NoAPIKeysError):
        APIKeyRotator()