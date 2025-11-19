"""
Rotation strategies tests for APIKeyRotator
Tests: RoundRobin, Random, Weighted, LRU, HealthBased strategies
"""

import pytest
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apikeyrotator.strategies import (
    create_rotation_strategy,
    RoundRobinRotationStrategy,
    RandomRotationStrategy,
    WeightedRotationStrategy,
    LRURotationStrategy,
    HealthBasedStrategy,
    KeyMetrics,
)


# ============================================================================
# ROUND ROBIN STRATEGY TESTS
# ============================================================================

class TestRoundRobinStrategy:
    """Test RoundRobinRotationStrategy."""

    def test_round_robin_order(self):
        strategy = RoundRobinRotationStrategy(['key1', 'key2', 'key3'])

        assert strategy.get_next_key() == 'key1'
        assert strategy.get_next_key() == 'key2'
        assert strategy.get_next_key() == 'key3'
        assert strategy.get_next_key() == 'key1'  # Should cycle back

    def test_round_robin_with_two_keys(self):
        strategy = RoundRobinRotationStrategy(['key1', 'key2'])

        keys = [strategy.get_next_key() for _ in range(6)]
        assert keys == ['key1', 'key2', 'key1', 'key2', 'key1', 'key2']

    def test_round_robin_with_single_key(self):
        strategy = RoundRobinRotationStrategy(['key1'])

        for _ in range(5):
            assert strategy.get_next_key() == 'key1'

    def test_round_robin_with_metrics(self):
        strategy = RoundRobinRotationStrategy(['key1', 'key2'])

        metrics = {
            'key1': KeyMetrics('key1'),
            'key2': KeyMetrics('key2')
        }

        # Mark key1 as unhealthy
        metrics['key1'].is_healthy = False

        # Should only return key2
        key = strategy.get_next_key(metrics)
        assert key == 'key2'


# ============================================================================
# RANDOM STRATEGY TESTS
# ============================================================================

class TestRandomStrategy:
    """Test RandomRotationStrategy."""

    def test_random_selection(self):
        strategy = RandomRotationStrategy(['key1', 'key2', 'key3'])

        keys = [strategy.get_next_key() for _ in range(30)]

        # All keys should appear at least once
        assert 'key1' in keys
        assert 'key2' in keys
        assert 'key3' in keys

        # Should have some randomness
        assert len(set(keys)) > 1

    def test_random_distribution(self):
        strategy = RandomRotationStrategy(['key1', 'key2'])

        keys = [strategy.get_next_key() for _ in range(1000)]

        count_key1 = keys.count('key1')
        count_key2 = keys.count('key2')

        # Should be roughly 50/50 distribution (allow 20% variance)
        assert 400 < count_key1 < 600
        assert 400 < count_key2 < 600

    def test_random_with_single_key(self):
        strategy = RandomRotationStrategy(['key1'])

        keys = [strategy.get_next_key() for _ in range(10)]
        assert all(k == 'key1' for k in keys)


# ============================================================================
# WEIGHTED STRATEGY TESTS
# ============================================================================

class TestWeightedStrategy:
    """Test WeightedRotationStrategy."""

    def test_weighted_distribution(self):
        strategy = WeightedRotationStrategy({
            'key1': 1,
            'key2': 2,
            'key3': 3
        })

        keys = [strategy.get_next_key() for _ in range(600)]

        count_key3 = keys.count('key3')
        count_key2 = keys.count('key2')
        count_key1 = keys.count('key1')

        # key3 should appear most, key1 least
        assert count_key3 > count_key2 > count_key1

    def test_weighted_with_equal_weights(self):
        strategy = WeightedRotationStrategy({
            'key1': 1,
            'key2': 1
        })

        keys = [strategy.get_next_key() for _ in range(200)]

        # Should be roughly equal (allow 30% variance)
        assert 70 < keys.count('key1') < 130
        assert 70 < keys.count('key2') < 130

    def test_weighted_extreme_weights(self):
        strategy = WeightedRotationStrategy({
            'key1': 1,
            'key2': 99
        })

        keys = [strategy.get_next_key() for _ in range(1000)]

        count_key2 = keys.count('key2')

        # key2 should dominate (at least 90%)
        assert count_key2 > 900

    def test_weighted_fractional_weights(self):
        strategy = WeightedRotationStrategy({
            'key1': 0.25,
            'key2': 0.75
        })

        keys = [strategy.get_next_key() for _ in range(400)]

        count_key1 = keys.count('key1')
        count_key2 = keys.count('key2')

        # key2 should appear 3x more than key1
        assert count_key2 > count_key1 * 2


# ============================================================================
# LRU STRATEGY TESTS
# ============================================================================

class TestLRUStrategy:
    """Test LRURotationStrategy."""

    def test_lru_basic_selection(self):
        strategy = LRURotationStrategy(['key1', 'key2', 'key3'])

        # First calls should return keys in order (all have last_used=0)
        key1 = strategy.get_next_key()
        key2 = strategy.get_next_key()
        key3 = strategy.get_next_key()

        # Fourth call should return oldest (key1)
        key4 = strategy.get_next_key()

        assert key1 in ['key1', 'key2', 'key3']
        assert key2 in ['key1', 'key2', 'key3']
        assert key3 in ['key1', 'key2', 'key3']
        assert key4 in ['key1', 'key2', 'key3']

    def test_lru_with_metrics(self):
        strategy = LRURotationStrategy(['key1', 'key2'])

        metrics = {
            'key1': KeyMetrics('key1'),
            'key2': KeyMetrics('key2')
        }

        # Simulate key1 being used recently
        metrics['key1'].last_used = time.time()
        metrics['key2'].last_used = time.time() - 100

        # Should return key2 (least recently used)
        key = strategy.get_next_key(metrics)
        assert key == 'key2'

    def test_lru_prevents_starvation(self):
        """LRU should eventually use all keys."""
        strategy = LRURotationStrategy(['key1', 'key2', 'key3'])

        keys_used = set()
        for _ in range(10):
            key = strategy.get_next_key()
            keys_used.add(key)

        # All keys should be used
        assert keys_used == {'key1', 'key2', 'key3'}


# ============================================================================
# HEALTH BASED STRATEGY TESTS
# ============================================================================

class TestHealthBasedStrategy:
    """Test HealthBasedStrategy."""

    def test_health_based_initialization(self):
        strategy = HealthBasedStrategy(
            ['key1', 'key2', 'key3'],
            failure_threshold=5,
            health_check_interval=300
        )

        assert strategy.failure_threshold == 5
        assert strategy.health_check_interval == 300
        assert len(strategy._key_metrics) == 3

    def test_healthy_key_selection(self):
        strategy = HealthBasedStrategy(['key1', 'key2', 'key3'])

        # All keys should be healthy initially
        key = strategy.get_next_key()
        assert key in ['key1', 'key2', 'key3']

    def test_unhealthy_key_exclusion(self):
        strategy = HealthBasedStrategy(['key1', 'key2'], failure_threshold=3)

        # Make key1 unhealthy
        for _ in range(3):
            strategy.update_key_metrics('key1', success=False)

        metrics = strategy._key_metrics

        # Should prefer key2 over unhealthy key1
        keys = [strategy.get_next_key(metrics) for _ in range(10)]

        # key2 should appear more often than key1
        assert keys.count('key2') > keys.count('key1')

    def test_health_recovery(self):
        strategy = HealthBasedStrategy(
            ['key1', 'key2'],
            failure_threshold=2,
            health_check_interval=0  # Immediate recheck
        )

        # Make key1 unhealthy
        strategy.update_key_metrics('key1', success=False)
        strategy.update_key_metrics('key1', success=False)

        assert strategy._key_metrics['key1'].is_healthy is False

        # Successful request should restore health
        strategy.update_key_metrics('key1', success=True)

        # After successful request, consecutive_failures should reset
        assert strategy._key_metrics['key1'].consecutive_failures == 0

    def test_all_keys_unhealthy_recovery(self):
        strategy = HealthBasedStrategy(['key1', 'key2'], failure_threshold=1)

        # Make both keys unhealthy
        strategy.update_key_metrics('key1', success=False)
        strategy.update_key_metrics('key2', success=False)

        # Should still return a key (resets all to healthy)
        key = strategy.get_next_key()
        assert key in ['key1', 'key2']


# ============================================================================
# KEY METRICS TESTS
# ============================================================================

class TestKeyMetrics:
    """Test KeyMetrics functionality."""

    def test_key_metrics_initialization(self):
        metrics = KeyMetrics("key1")
        assert metrics.key == "key1"
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.is_healthy is True
        assert metrics.success_rate == 1.0

    def test_update_successful_request(self):
        metrics = KeyMetrics("key1")
        metrics.update_from_request(success=True, response_time=0.5)

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.consecutive_failures == 0
        assert metrics.is_healthy is True

    def test_update_failed_request(self):
        metrics = KeyMetrics("key1")
        metrics.update_from_request(success=False, response_time=0.5)

        assert metrics.total_requests == 1
        assert metrics.failed_requests == 1
        assert metrics.consecutive_failures == 1

    def test_health_status_on_multiple_failures(self):
        metrics = KeyMetrics("key1")

        # Fail 3 times - should become unhealthy
        for _ in range(3):
            metrics.update_from_request(success=False, response_time=0.5)

        assert metrics.consecutive_failures == 3
        assert metrics.is_healthy is False

    def test_ewma_calculation(self):
        metrics = KeyMetrics("key1", ewma_alpha=0.5)

        # Success
        metrics.update_from_request(success=True, response_time=0.1)
        first_rate = metrics.success_rate

        # Another success
        metrics.update_from_request(success=True, response_time=0.1)

        # Success rate should be high
        assert metrics.success_rate > 0.7

    def test_consecutive_failures_reset_on_success(self):
        metrics = KeyMetrics("key1")

        # Fail twice
        metrics.update_from_request(success=False, response_time=0.5)
        metrics.update_from_request(success=False, response_time=0.5)
        assert metrics.consecutive_failures == 2

        # Success should reset
        metrics.update_from_request(success=True, response_time=0.5)
        assert metrics.consecutive_failures == 0

    def test_get_score(self):
        metrics = KeyMetrics("key1")

        # Add some successful requests
        for _ in range(10):
            metrics.update_from_request(success=True, response_time=0.2)

        score = metrics.get_score()
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should have good score

    def test_get_score_unhealthy_key(self):
        metrics = KeyMetrics("key1")

        # Make unhealthy
        for _ in range(5):
            metrics.update_from_request(success=False, response_time=0.5)

        score = metrics.get_score()
        assert score == 0.0  # Unhealthy key should have 0 score

    def test_to_dict_serialization(self):
        metrics = KeyMetrics("key1")
        metrics.update_from_request(success=True, response_time=0.5)

        data = metrics.to_dict()

        assert data['key'] == 'key1'
        assert data['total_requests'] == 1
        assert data['successful_requests'] == 1
        assert data['is_healthy'] is True
        assert 'success_rate' in data
        assert 'avg_response_time' in data


# ============================================================================
# STRATEGY FACTORY TESTS
# ============================================================================

class TestStrategyFactory:
    """Test strategy factory function."""

    def test_create_round_robin(self):
        strategy = create_rotation_strategy('round_robin', ['key1', 'key2'])
        assert isinstance(strategy, RoundRobinRotationStrategy)

    def test_create_random(self):
        strategy = create_rotation_strategy('random', ['key1', 'key2'])
        assert isinstance(strategy, RandomRotationStrategy)

    def test_create_weighted(self):
        strategy = create_rotation_strategy('weighted', {'key1': 1, 'key2': 2})
        assert isinstance(strategy, WeightedRotationStrategy)

    def test_create_lru(self):
        strategy = create_rotation_strategy('lru', ['key1', 'key2'])
        assert isinstance(strategy, LRURotationStrategy)

    def test_create_health_based(self):
        strategy = create_rotation_strategy('health_based', ['key1', 'key2'])
        assert isinstance(strategy, HealthBasedStrategy)

    def test_invalid_strategy(self):
        with pytest.raises(ValueError):
            create_rotation_strategy('invalid_strategy', ['key1'])

    def test_strategy_with_kwargs(self):
        strategy = create_rotation_strategy(
            'health_based',
            ['key1', 'key2'],
            failure_threshold=10,
            health_check_interval=600
        )
        assert isinstance(strategy, HealthBasedStrategy)
        assert strategy.failure_threshold == 10
        assert strategy.health_check_interval == 600

    def test_weighted_strategy_requires_dict(self):
        # Weighted strategy requires dict
        with pytest.raises(ValueError):
            create_rotation_strategy('weighted', ['key1', 'key2'])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])