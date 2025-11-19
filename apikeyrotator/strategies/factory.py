"""
Factory for creating rotation strategies
"""

from typing import Union, List, Dict
from .base import BaseRotationStrategy, RotationStrategy
from .round_robin import RoundRobinRotationStrategy
from .random import RandomRotationStrategy
from .weighted import WeightedRotationStrategy
from .lru import LRURotationStrategy
from .health_based import HealthBasedStrategy


def create_rotation_strategy(
        strategy_type: Union[str, RotationStrategy],
        keys: Union[List[str], Dict[str, float]],
        **kwargs
) -> BaseRotationStrategy:
    """
    Factory function for creating a rotation strategy.

    Args:
        strategy_type: Strategy type ('round_robin', 'random', 'weighted', 'lru', 'health_based')
                       or RotationStrategy enum instance
        keys: List of keys or weight dictionary for weighted strategy
        **kwargs: Additional parameters for specific strategy

    Returns:
        BaseRotationStrategy: Rotation strategy instance

    Raises:
        ValueError: If strategy type is unknown or parameters are invalid

    Examples:
        >>> # Round Robin
        >>> strategy = create_rotation_strategy('round_robin', ['key1', 'key2'])

        >>> # Random
        >>> strategy = create_rotation_strategy('random', ['key1', 'key2'])

        >>> # Weighted
        >>> strategy = create_rotation_strategy('weighted', {'key1': 0.7, 'key2': 0.3})

        >>> # LRU
        >>> strategy = create_rotation_strategy('lru', ['key1', 'key2'])

        >>> # Health-Based with parameters
        >>> strategy = create_rotation_strategy(
        ...     'health_based',
        ...     ['key1', 'key2'],
        ...     failure_threshold=5,
        ...     health_check_interval=300
        ... )

        >>> # Using enum
        >>> from .base import RotationStrategy
        >>> strategy = create_rotation_strategy(
        ...     RotationStrategy.ROUND_ROBIN,
        ...     ['key1', 'key2']
        ... )
    """
    # Normalize strategy type
    if isinstance(strategy_type, str):
        strategy_type = strategy_type.lower()
    else:
        strategy_type = strategy_type.value

    # Strategy mapping
    strategy_map = {
        "round_robin": RoundRobinRotationStrategy,
        "random": RandomRotationStrategy,
        "weighted": WeightedRotationStrategy,
        "lru": LRURotationStrategy,
        "health_based": HealthBasedStrategy,
    }

    # Find strategy class
    strategy_class = strategy_map.get(strategy_type)
    if not strategy_class:
        available = ', '.join(strategy_map.keys())
        raise ValueError(
            f"Unknown rotation strategy: {strategy_type}. "
            f"Available strategies: {available}"
        )

    # Validation for weighted strategy
    if strategy_type == "weighted":
        if not isinstance(keys, dict):
            raise ValueError(
                "Weighted strategy requires a dictionary of keys with weights. "
                "Example: {'key1': 0.7, 'key2': 0.3}"
            )
        if not keys:
            raise ValueError("Weighted strategy requires at least one key with weight")

    # Create strategy instance
    return strategy_class(keys, **kwargs)