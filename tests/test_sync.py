import pytest
import requests_mock
from apikeyrotator import APIKeyRotator, AllKeysExhaustedError


def test_successful_get_request(requests_mock):
    url = "https://api.example.com/data"
    requests_mock.get(url, json={"status": "ok"}, status_code=200)

    rotator = APIKeyRotator(api_keys=["test_key"])
    response = rotator.get(url)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "Authorization" in requests_mock.last_request.headers
    assert requests_mock.last_request.headers["Authorization"] == "Bearer test_key"