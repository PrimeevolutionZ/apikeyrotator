"""Metric exporters to various formats"""

from .collector import RotatorMetrics
from typing import Optional, Dict, Any


class PrometheusExporter:
    """Metrics exporter in Prometheus format"""

    @staticmethod
    def export(metrics: RotatorMetrics, key_metrics: Optional[Dict[str, Any]] = None) -> str:
        """
        Exports metrics in Prometheus format.

        Args:
            metrics: RotatorMetrics instance
            key_metrics: Optional dict with key statistics from rotator.get_key_statistics()

        Returns:
            str: Metrics in Prometheus format
        """
        output = []

        # General metrics
        output.append("# HELP rotator_total_requests Total requests")
        output.append("# TYPE rotator_total_requests counter")
        output.append(f"rotator_total_requests {metrics.total_requests}")

        output.append("# HELP rotator_successful_requests Successful requests")
        output.append("# TYPE rotator_successful_requests counter")
        output.append(f"rotator_successful_requests {metrics.successful_requests}")

        output.append("# HELP rotator_failed_requests Failed requests")
        output.append("# TYPE rotator_failed_requests counter")
        output.append(f"rotator_failed_requests {metrics.failed_requests}")

        # Per-key metrics (if provided)
        if key_metrics:
            for key, stats in key_metrics.items():
                key_label = key[:8] + "..."

                output.append(f"# HELP rotator_key_total_requests Total requests for key")
                output.append(f"# TYPE rotator_key_total_requests counter")
                output.append(f'rotator_key_total_requests{{key="{key_label}"}} {stats.get("total_requests", 0)}')

                output.append(f'rotator_key_successful_requests{{key="{key_label}"}} {stats.get("successful_requests", 0)}')
                output.append(f'rotator_key_failed_requests{{key="{key_label}"}} {stats.get("failed_requests", 0)}')
                output.append(f'rotator_key_avg_response_time_seconds{{key="{key_label}"}} {stats.get("avg_response_time", 0.0)}')
                output.append(f'rotator_key_rate_limit_hits_total{{key="{key_label}"}} {stats.get("rate_limit_hits", 0)}')
                output.append(f'rotator_key_is_healthy{{key="{key_label}"}} {1 if stats.get("is_healthy", True) else 0}')

        # Per-endpoint metrics
        for endpoint, stats in metrics.endpoint_stats.items():
            stats_dict = stats.to_dict()
            output.append(f'rotator_endpoint_total_requests{{endpoint="{endpoint}"}} {stats_dict["total_requests"]}')
            output.append(f'rotator_endpoint_successful_requests{{endpoint="{endpoint}"}} {stats_dict["successful_requests"]}')
            output.append(f'rotator_endpoint_failed_requests{{endpoint="{endpoint}"}} {stats_dict["failed_requests"]}')
            output.append(f'rotator_endpoint_avg_response_time_seconds{{endpoint="{endpoint}"}} {stats_dict["avg_response_time"]}')

        return "\n".join(output)