"""Экспортеры метрик в различные форматы"""

from .collector import RotatorMetrics


class PrometheusExporter:
    """Экспортер метрик в формат Prometheus"""

    @staticmethod
    def export(metrics: RotatorMetrics) -> str:
        """
        Экспортирует метрики в формат Prometheus.

        Args:
            metrics: Экземпляр RotatorMetrics

        Returns:
            str: Метрики в формате Prometheus
        """
        output = []

        # Общие метрики
        output.append("# HELP rotator_total_requests Total requests")
        output.append("# TYPE rotator_total_requests counter")
        output.append(f"rotator_total_requests {metrics.total_requests}")

        output.append("# HELP rotator_successful_requests Successful requests")
        output.append("# TYPE rotator_successful_requests counter")
        output.append(f"rotator_successful_requests {metrics.successful_requests}")

        output.append("# HELP rotator_failed_requests Failed requests")
        output.append("# TYPE rotator_failed_requests counter")
        output.append(f"rotator_failed_requests {metrics.failed_requests}")

        # Метрики по ключам
        for key, stats in metrics.key_stats.items():
            key_label = key[:8] + "..."

            output.append(f"# HELP rotator_key_total_requests Total requests for key")
            output.append(f"# TYPE rotator_key_total_requests counter")
            output.append(f'rotator_key_total_requests{{key="{key_label}"}} {stats.total_requests}')

            output.append(f'rotator_key_successful_requests{{key="{key_label}"}} {stats.successful_requests}')
            output.append(f'rotator_key_failed_requests{{key="{key_label}"}} {stats.failed_requests}')
            output.append(f'rotator_key_avg_response_time_seconds{{key="{key_label}"}} {stats.avg_response_time}')
            output.append(f'rotator_key_rate_limit_hits_total{{key="{key_label}"}} {stats.rate_limit_hits}')
            output.append(f'rotator_key_is_healthy{{key="{key_label}"}} {1 if stats.is_healthy else 0}')

        # Метрики по endpoint
        for endpoint, stats in metrics.endpoint_stats.items():
            output.append(f'rotator_endpoint_total_requests{{endpoint="{endpoint}"}} {stats.total_requests}')
            output.append(f'rotator_endpoint_successful_requests{{endpoint="{endpoint}"}} {stats.successful_requests}')
            output.append(f'rotator_endpoint_failed_requests{{endpoint="{endpoint}"}} {stats.failed_requests}')
            output.append(
                f'rotator_endpoint_avg_response_time_seconds{{endpoint="{endpoint}"}} {stats.avg_response_time}')

        return "\n".join(output)