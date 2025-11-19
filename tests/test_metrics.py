"""
Metrics and monitoring tests for APIKeyRotator
Tests: RotatorMetrics, PrometheusExporter, ErrorClassifier
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import MagicMock

from apikeyrotator import ErrorClassifier, ErrorType
from apikeyrotator.metrics import RotatorMetrics, PrometheusExporter

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ============================================================================
# ROTATOR METRICS TESTS
# ============================================================================

class TestRotatorMetrics:
    """Test RotatorMetrics functionality."""

    def test_metrics_initialization(self):
        metrics = RotatorMetrics()
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert len(metrics.endpoint_stats) == 0

    def test_record_successful_request(self):
        metrics = RotatorMetrics()
        metrics.record_request(
            key="key1",
            endpoint="http://example.com",
            success=True,
            response_time=0.5,
            is_rate_limited=False
        )

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0

    def test_record_failed_request(self):
        metrics = RotatorMetrics()
        metrics.record_request(
            key="key1",
            endpoint="http://example.com",
            success=False,
            response_time=0.5,
            is_rate_limited=False
        )

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1

    def test_record_rate_limited_request(self):
        metrics = RotatorMetrics()
        metrics.record_request(
            key="key1",
            endpoint="http://example.com",
            success=False,
            response_time=0.5,
            is_rate_limited=True
        )

        assert metrics.total_requests == 1
        assert metrics.failed_requests == 1

    def test_endpoint_statistics(self):
        metrics = RotatorMetrics()

        # Make requests to same endpoint
        for i in range(10):
            metrics.record_request(
                key="key1",
                endpoint="http://example.com/api",
                success=i % 2 == 0,  # Alternate success/failure
                response_time=0.1 * i,
                is_rate_limited=False
            )

        endpoint_stats = metrics.get_endpoint_stats("http://example.com/api")
        assert endpoint_stats['total_requests'] == 10
        assert endpoint_stats['successful_requests'] == 5
        assert endpoint_stats['failed_requests'] == 5

    def test_multiple_endpoints(self):
        metrics = RotatorMetrics()

        # Make requests to different endpoints
        metrics.record_request("key1", "http://example.com/api1", True, 0.1)
        metrics.record_request("key1", "http://example.com/api2", True, 0.2)
        metrics.record_request("key1", "http://example.com/api1", True, 0.1)

        assert len(metrics.endpoint_stats) == 2
        assert metrics.get_endpoint_stats("http://example.com/api1")['total_requests'] == 2
        assert metrics.get_endpoint_stats("http://example.com/api2")['total_requests'] == 1

    def test_get_metrics(self):
        metrics = RotatorMetrics()

        metrics.record_request("key1", "http://example.com", True, 0.5)
        metrics.record_request("key1", "http://example.com", False, 0.5)

        result = metrics.get_metrics()

        assert result['total_requests'] == 2
        assert result['successful_requests'] == 1
        assert result['failed_requests'] == 1
        assert result['success_rate'] == 0.5
        assert 'uptime_seconds' in result
        assert 'endpoint_stats' in result

    def test_get_top_endpoints(self):
        metrics = RotatorMetrics()

        # Create requests with different frequencies
        for _ in range(10):
            metrics.record_request("key1", "http://example.com/popular", True, 0.1)

        for _ in range(5):
            metrics.record_request("key1", "http://example.com/medium", True, 0.1)

        for _ in range(2):
            metrics.record_request("key1", "http://example.com/rare", True, 0.1)

        top = metrics.get_top_endpoints(limit=2)

        assert len(top) == 2
        assert top[0][0] == "http://example.com/popular"
        assert top[0][1] == 10
        assert top[1][0] == "http://example.com/medium"
        assert top[1][1] == 5

    def test_reset_metrics(self):
        metrics = RotatorMetrics()

        metrics.record_request("key1", "http://example.com", True, 0.5)
        metrics.record_request("key1", "http://example.com", False, 0.5)

        assert metrics.total_requests == 2

        metrics.reset()

        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert len(metrics.endpoint_stats) == 0

    def test_success_rate_calculation(self):
        metrics = RotatorMetrics()

        # 7 successful, 3 failed
        for _ in range(7):
            metrics.record_request("key1", "http://example.com", True, 0.1)
        for _ in range(3):
            metrics.record_request("key1", "http://example.com", False, 0.1)

        result = metrics.get_metrics()
        assert result['success_rate'] == 0.7


# ============================================================================
# PROMETHEUS EXPORTER TESTS
# ============================================================================

class TestPrometheusExporter:
    """Test PrometheusExporter functionality."""

    def test_prometheus_export_basic(self):
        metrics = RotatorMetrics()
        metrics.record_request("key1", "http://example.com", True, 0.5)

        exporter = PrometheusExporter()
        output = exporter.export(metrics)

        assert "rotator_total_requests" in output
        assert "rotator_successful_requests" in output
        assert "rotator_failed_requests" in output

    def test_prometheus_format(self):
        metrics = RotatorMetrics()
        metrics.record_request("key1", "http://example.com", True, 0.5)

        exporter = PrometheusExporter()
        output = exporter.export(metrics)

        # Check Prometheus format
        lines = output.split('\n')

        # Should have HELP and TYPE comments
        help_lines = [l for l in lines if l.startswith('# HELP')]
        type_lines = [l for l in lines if l.startswith('# TYPE')]

        assert len(help_lines) > 0
        assert len(type_lines) > 0

    def test_prometheus_with_multiple_endpoints(self):
        metrics = RotatorMetrics()

        metrics.record_request("key1", "http://example.com/api1", True, 0.1)
        metrics.record_request("key1", "http://example.com/api2", True, 0.2)

        exporter = PrometheusExporter()
        output = exporter.export(metrics)

        # Should contain endpoint metrics
        assert "rotator_endpoint_total_requests" in output or "endpoint" in output


# ============================================================================
# ERROR CLASSIFIER TESTS
# ============================================================================

class TestErrorClassifier:
    """Test ErrorClassifier functionality."""

    def test_classify_rate_limit(self):
        classifier = ErrorClassifier()
        response = MagicMock(status_code=429)

        assert classifier.classify_error(response=response) == ErrorType.RATE_LIMIT

    def test_classify_temporary_5xx(self):
        classifier = ErrorClassifier()

        for code in [500, 502, 503, 504, 507]:
            response = MagicMock(status_code=code)
            assert classifier.classify_error(response=response) == ErrorType.TEMPORARY

    def test_classify_temporary_special_4xx(self):
        classifier = ErrorClassifier()

        # 408, 409, 425 should be temporary (new in 0.4.3)
        for code in [408, 409, 425]:
            response = MagicMock(status_code=code)
            assert classifier.classify_error(response=response) == ErrorType.TEMPORARY

    def test_classify_permanent_auth(self):
        classifier = ErrorClassifier()

        for code in [401, 403]:
            response = MagicMock(status_code=code)
            assert classifier.classify_error(response=response) == ErrorType.PERMANENT

    def test_classify_permanent_not_found(self):
        classifier = ErrorClassifier()

        for code in [404, 410]:
            response = MagicMock(status_code=code)
            assert classifier.classify_error(response=response) == ErrorType.PERMANENT

    def test_classify_permanent_bad_request(self):
        classifier = ErrorClassifier()

        for code in [400, 405, 406, 422]:
            response = MagicMock(status_code=code)
            assert classifier.classify_error(response=response) == ErrorType.PERMANENT

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_classify_network_error(self):
        classifier = ErrorClassifier()

        assert classifier.classify_error(
            exception=requests.exceptions.ConnectionError()
        ) == ErrorType.NETWORK

        assert classifier.classify_error(
            exception=requests.exceptions.Timeout()
        ) == ErrorType.NETWORK

        assert classifier.classify_error(
            exception=requests.exceptions.ConnectTimeout()
        ) == ErrorType.NETWORK

    def test_classify_unknown_error(self):
        classifier = ErrorClassifier()

        # 200 is not an error
        assert classifier.classify_error(
            response=MagicMock(status_code=200)
        ) == ErrorType.UNKNOWN

        # Unknown exception
        assert classifier.classify_error(
            exception=ValueError("test")
        ) == ErrorType.UNKNOWN

    def test_custom_retryable_codes(self):
        classifier = ErrorClassifier(custom_retryable_codes=[420, 509])

        response = MagicMock(status_code=420)
        assert classifier.classify_error(response=response) == ErrorType.TEMPORARY

        response = MagicMock(status_code=509)
        assert classifier.classify_error(response=response) == ErrorType.TEMPORARY

    def test_is_retryable(self):
        classifier = ErrorClassifier()

        # Should retry
        assert classifier.is_retryable(response=MagicMock(status_code=429))
        assert classifier.is_retryable(response=MagicMock(status_code=503))
        assert classifier.is_retryable(response=MagicMock(status_code=408))

        # Should not retry
        assert not classifier.is_retryable(response=MagicMock(status_code=400))
        assert not classifier.is_retryable(response=MagicMock(status_code=401))
        assert not classifier.is_retryable(response=MagicMock(status_code=404))

    def test_should_switch_key(self):
        classifier = ErrorClassifier()

        # Should switch on rate limit
        assert classifier.should_switch_key(response=MagicMock(status_code=429))

        # Should switch on auth errors
        assert classifier.should_switch_key(response=MagicMock(status_code=401))
        assert classifier.should_switch_key(response=MagicMock(status_code=403))

        # Should not switch on temporary errors
        assert not classifier.should_switch_key(response=MagicMock(status_code=503))

    def test_should_remove_key(self):
        classifier = ErrorClassifier()

        # Should remove on auth errors
        assert classifier.should_remove_key(response=MagicMock(status_code=401))
        assert classifier.should_remove_key(response=MagicMock(status_code=403))

        # Should not remove on other errors
        assert not classifier.should_remove_key(response=MagicMock(status_code=429))
        assert not classifier.should_remove_key(response=MagicMock(status_code=503))
        assert not classifier.should_remove_key(response=MagicMock(status_code=404))

    def test_get_retry_delay_default(self):
        classifier = ErrorClassifier()

        # No retry-after header
        response = MagicMock(status_code=503, headers={})
        delay = classifier.get_retry_delay(response, default_delay=1.0)
        assert delay == 1.0

    def test_get_retry_delay_with_header(self):
        classifier = ErrorClassifier()

        # With retry-after header (seconds)
        response = MagicMock(status_code=429, headers={'Retry-After': '60'})
        delay = classifier.get_retry_delay(response)
        assert delay == 60.0

    def test_get_retry_delay_rate_limit_multiplier(self):
        classifier = ErrorClassifier()

        # Rate limit should use longer delay
        response = MagicMock(status_code=429, headers={})
        delay = classifier.get_retry_delay(response, default_delay=1.0)
        assert delay == 5.0  # default_delay * 5 for rate limits


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])