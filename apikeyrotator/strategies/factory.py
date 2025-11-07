"""
Фабрика для создания стратегий ротации
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
    Фабричная функция для создания стратегии ротации.

    Args:
        strategy_type: Тип стратегии ('round_robin', 'random', 'weighted', 'lru', 'health_based')
                       или экземпляр RotationStrategy enum
        keys: Список ключей или словарь с весами для weighted стратегии
        **kwargs: Дополнительные параметры для конкретной стратегии

    Returns:
        BaseRotationStrategy: Экземпляр стратегии ротации

    Raises:
        ValueError: Если тип стратегии неизвестен или параметры некорректны

    Examples:
        >>> # Round Robin
        >>> strategy = create_rotation_strategy('round_robin', ['key1', 'key2'])

        >>> # Random
        >>> strategy = create_rotation_strategy('random', ['key1', 'key2'])

        >>> # Weighted
        >>> strategy = create_rotation_strategy('weighted', {'key1': 0.7, 'key2': 0.3})

        >>> # LRU
        >>> strategy = create_rotation_strategy('lru', ['key1', 'key2'])

        >>> # Health-Based с параметрами
        >>> strategy = create_rotation_strategy(
        ...     'health_based',
        ...     ['key1', 'key2'],
        ...     failure_threshold=5,
        ...     health_check_interval=300
        ... )

        >>> # Используя enum
        >>> from .base import RotationStrategy
        >>> strategy = create_rotation_strategy(
        ...     RotationStrategy.ROUND_ROBIN,
        ...     ['key1', 'key2']
        ... )
    """
    # Нормализуем тип стратегии
    if isinstance(strategy_type, str):
        strategy_type = strategy_type.lower()
    else:
        strategy_type = strategy_type.value

    # Маппинг стратегий
    strategy_map = {
        "round_robin": RoundRobinRotationStrategy,
        "random": RandomRotationStrategy,
        "weighted": WeightedRotationStrategy,
        "lru": LRURotationStrategy,
        "health_based": HealthBasedStrategy,
    }

    # Находим класс стратегии
    strategy_class = strategy_map.get(strategy_type)
    if not strategy_class:
        available = ', '.join(strategy_map.keys())
        raise ValueError(
            f"Unknown rotation strategy: {strategy_type}. "
            f"Available strategies: {available}"
        )

    # Валидация для weighted стратегии
    if strategy_type == "weighted":
        if not isinstance(keys, dict):
            raise ValueError(
                "Weighted strategy requires a dictionary of keys with weights. "
                "Example: {'key1': 0.7, 'key2': 0.3}"
            )
        if not keys:
            raise ValueError("Weighted strategy requires at least one key with weight")

    # Создаем экземпляр стратегии
    return strategy_class(keys, **kwargs)