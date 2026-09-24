"""
Requests with side effects (payments, orders, messages, webhooks): a POST/PATCH
must never be executed twice because of the rotator.
"""

from unittest.mock import Mock, patch

import pytest
import requests

from apikeyrotator import (
    AllKeysExhaustedError,
    APIKeyRotator,
    FallbackRouter,
    ProviderRoute,
)


def resp(status, headers=None, body=b"{}"):
    return Mock(status_code=status, headers=headers or {}, content=body)


def keys_used(mock_request):
    return [c[1]["headers"]["Authorization"].replace("Bearer ", "") for c in mock_request.call_args_list]


def make(**kwargs):
    kwargs.setdefault("api_keys", ["key_a", "key_b"])
    kwargs.setdefault("base_delay", 0.001)
    return APIKeyRotator(**kwargs)


class TestNoDuplicateExecution:
    @pytest.mark.parametrize("status", [500, 502, 504])
    def test_post_is_not_retried_after_an_ambiguous_status(self, status):
        rotator = make()
        with patch("requests.Session.request", return_value=resp(status)) as mock_request:
            assert rotator.post("https://api.example.com/pay", json={}).status_code == status
        assert mock_request.call_count == 1

    @pytest.mark.parametrize("status", [429, 503, 408, 425])
    def test_post_is_retried_when_the_server_did_not_process_it(self, status):
        rotator = make()
        with patch("requests.Session.request", side_effect=[resp(status), resp(201)]) as mock_request:
            assert rotator.post("https://api.example.com/pay", json={}).status_code == 201
        assert mock_request.call_count == 2

    def test_post_read_timeout_is_re_raised(self):
        rotator = make()
        with patch("requests.Session.request", side_effect=requests.ReadTimeout("slow")) as mock_request:
            with pytest.raises(requests.ReadTimeout):
                rotator.post("https://api.example.com/pay", json={})
        assert mock_request.call_count == 1

    def test_should_retry_callback_cannot_repeat_an_executed_post(self):
        rotator = make(should_retry_callback=lambda response: True)
        with patch("requests.Session.request", return_value=resp(200)) as mock_request:
            assert rotator.post("https://api.example.com/pay", json={}).status_code == 200
        assert mock_request.call_count == 1

    def test_should_retry_callback_still_retries_get(self):
        answers = iter([True, False])
        rotator = make(should_retry_callback=lambda response: next(answers))
        with patch("requests.Session.request", return_value=resp(200)) as mock_request:
            rotator.get("https://api.example.com/items")
        assert mock_request.call_count == 2


class TestIdempotentRetries:
    def test_ambiguous_retry_reuses_the_same_key(self):
        """Idempotency keys are scoped to the API key's account: switching keys would defeat them."""
        rotator = make()
        with patch("requests.Session.request", side_effect=[resp(500), resp(500), resp(201)]) as mock_request:
            response = rotator.post("https://api.example.com/pay", json={},
                                    headers={"Idempotency-Key": "order-42"})
        assert response.status_code == 201
        assert keys_used(mock_request) == ["key_a", "key_a", "key_a"]

    def test_rate_limit_before_any_ambiguous_failure_may_switch_keys(self):
        rotator = make()
        with patch("requests.Session.request", side_effect=[resp(429), resp(201)]) as mock_request:
            rotator.post("https://api.example.com/pay", json={}, headers={"Idempotency-Key": "x"})
        assert keys_used(mock_request) == ["key_a", "key_b"]

    def test_pinned_key_waits_for_its_own_rate_limit(self, virtual_clock):
        rotator = make()
        with patch("requests.Session.request",
                   side_effect=[resp(500), resp(429, {"Retry-After": "7"}), resp(201)]) as mock_request:
            rotator.post("https://api.example.com/pay", json={}, headers={"Idempotency-Key": "x"})
        assert keys_used(mock_request) == ["key_a", "key_a", "key_a"]
        assert 7 in [round(s) for s in virtual_clock.sleeps]

    def test_exhausted_ambiguous_post_is_marked(self):
        rotator = make(max_retries=2)
        with patch("requests.Session.request", return_value=resp(500)):
            with pytest.raises(AllKeysExhaustedError) as exc:
                rotator.post("https://api.example.com/pay", json={}, headers={"Idempotency-Key": "x"})
        assert exc.value.possibly_processed is True

    def test_exhausted_after_rejections_only_is_not_marked(self):
        rotator = make(max_retries=2)
        with patch("requests.Session.request", return_value=resp(503)):
            with pytest.raises(AllKeysExhaustedError) as exc:
                rotator.post("https://api.example.com/pay", json={})
        assert exc.value.possibly_processed is False


class TestAutoIdempotencyKey:
    def test_generated_once_per_request_and_reused_on_retries(self):
        rotator = make(auto_idempotency_key=True)
        with patch("requests.Session.request", side_effect=[resp(500), resp(201)]) as mock_request:
            rotator.post("https://api.example.com/pay", json={})
        sent = [c[1]["headers"]["Idempotency-Key"] for c in mock_request.call_args_list]
        assert len(sent) == 2 and sent[0] == sent[1] and len(sent[0]) == 32

    def test_new_key_for_each_request(self):
        rotator = make(auto_idempotency_key=True)
        with patch("requests.Session.request", return_value=resp(201)) as mock_request:
            rotator.post("https://api.example.com/pay", json={})
            rotator.post("https://api.example.com/pay", json={})
        sent = [c[1]["headers"]["Idempotency-Key"] for c in mock_request.call_args_list]
        assert sent[0] != sent[1]

    def test_not_added_to_idempotent_methods_or_when_given(self):
        rotator = make(auto_idempotency_key="X-Request-Id")
        with patch("requests.Session.request", return_value=resp(200)) as mock_request:
            rotator.get("https://api.example.com/items")
            rotator.patch("https://api.example.com/items/1", json={}, headers={"x-request-id": "mine"})
            rotator.post("https://api.example.com/items", json={})
        calls = [c[1]["headers"] for c in mock_request.call_args_list]
        assert "X-Request-Id" not in calls[0]
        assert calls[1].get("x-request-id") == "mine" and "X-Request-Id" not in calls[1]
        assert "X-Request-Id" in calls[2]

    def test_caller_headers_are_not_mutated(self):
        rotator = make(auto_idempotency_key=True)
        headers = {"X-Trace": "1"}
        with patch("requests.Session.request", return_value=resp(201)):
            rotator.post("https://api.example.com/pay", json={}, headers=headers)
        assert headers == {"X-Trace": "1"}


class TestFallbackRouter:
    def _router(self, primary, secondary):
        return FallbackRouter([
            ProviderRoute(name="primary", rotator=primary),
            ProviderRoute(name="secondary", rotator=secondary),
        ])

    def test_does_not_resend_a_possibly_executed_post_to_another_provider(self):
        primary, secondary = make(max_retries=2), make(max_retries=2)
        router = self._router(primary, secondary)
        with patch("requests.Session.request", return_value=resp(500)) as mock_request:
            with pytest.raises(AllKeysExhaustedError) as exc:
                router.post("https://api.example.com/pay", json={}, headers={"Idempotency-Key": "x"})
        assert exc.value.possibly_processed
        assert mock_request.call_count == 2  # primary only

    def test_falls_back_when_the_first_provider_certainly_did_nothing(self):
        primary, secondary = make(max_retries=2), make(max_retries=2)
        router = self._router(primary, secondary)
        with patch("requests.Session.request", side_effect=[resp(503), resp(503), resp(201)]):
            assert router.post("https://api.example.com/pay", json={}).status_code == 201
