"""Metric exporters to various formats"""

from typing import Any

from .collector import RotatorMetrics


def _escape_label(value: str) -> str:
    """Escapes a Prometheus label value (backslash, double quote, newline)."""
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def _mask_key(key: str) -> str:
    from apikeyrotator.core.util import mask_key

    return mask_key(key) if len(key) > 4 else "****"


class PrometheusExporter:
    """Metrics exporter in Prometheus text exposition format"""

    @staticmethod
    def _family(
            output: list[str], name: str, help_text: str, metric_type: str,
            samples: list[tuple[str, Any]]
    ) -> None:
        """Appends one metric family (HELP/TYPE emitted exactly once)."""
        if not samples:
            return
        output.append(f"# HELP {name} {help_text}")
        output.append(f"# TYPE {name} {metric_type}")
        for labels, value in samples:
            output.append(f"{name}{labels} {value}")

    @staticmethod
    def export(metrics: RotatorMetrics, key_metrics: dict[str, Any] | None = None) -> str:
        """
        Exports metrics in Prometheus format.

        Args:
            metrics: RotatorMetrics instance
            key_metrics: Optional dict with key statistics from rotator.get_key_statistics()

        Returns:
            str: Metrics in Prometheus format
        """
        output: list[str] = []
        family = PrometheusExporter._family

        snapshot = metrics.get_metrics()

        family(output, "rotator_total_requests", "Total requests", "counter",
               [("", snapshot["total_requests"])])
        family(output, "rotator_successful_requests", "Successful requests", "counter",
               [("", snapshot["successful_requests"])])
        family(output, "rotator_failed_requests", "Failed requests", "counter",
               [("", snapshot["failed_requests"])])
        family(output, "rotator_uptime_seconds", "Rotator uptime in seconds", "gauge",
               [("", snapshot["uptime_seconds"])])

        # Per-key metrics (if provided). Keys are masked - never export secrets.
        if key_metrics:
            key_rows = []
            seen = {}
            for key, stats in key_metrics.items():
                label = _mask_key(key)
                seen[label] = seen.get(label, 0) + 1
                if seen[label] > 1:
                    label = f"{label}#{seen[label]}"
                key_rows.append((f'{{key="{_escape_label(label)}"}}', stats))

            per_key = [
                ("rotator_key_total_requests", "Total requests for key", "counter",
                 lambda st: st.get("total_requests", 0)),
                ("rotator_key_successful_requests", "Successful requests for key", "counter",
                 lambda st: st.get("successful_requests", 0)),
                ("rotator_key_failed_requests", "Failed requests for key", "counter",
                 lambda st: st.get("failed_requests", 0)),
                ("rotator_key_avg_response_time_seconds", "Average response time for key", "gauge",
                 lambda st: st.get("avg_response_time", 0.0)),
                ("rotator_key_rate_limit_hits_total", "Rate limit hits for key", "counter",
                 lambda st: st.get("rate_limit_hits", 0)),
                ("rotator_key_is_healthy", "Whether key is healthy (1) or not (0)", "gauge",
                 lambda st: 1 if st.get("is_healthy", True) else 0),
            ]
            for name, help_text, metric_type, getter in per_key:
                family(output, name, help_text, metric_type,
                       [(labels, getter(stats)) for labels, stats in key_rows])

        # Per-endpoint metrics
        endpoint_rows = [
            (f'{{endpoint="{_escape_label(endpoint)}"}}', stats)
            for endpoint, stats in snapshot["endpoint_stats"].items()
        ]
        per_endpoint = [
            ("rotator_endpoint_total_requests", "Total requests per endpoint", "counter", "total_requests"),
            ("rotator_endpoint_successful_requests", "Successful requests per endpoint", "counter",
             "successful_requests"),
            ("rotator_endpoint_failed_requests", "Failed requests per endpoint", "counter", "failed_requests"),
            ("rotator_endpoint_avg_response_time_seconds", "Average response time per endpoint", "gauge",
             "avg_response_time"),
        ]
        for name, help_text, metric_type, field in per_endpoint:
            family(output, name, help_text, metric_type,
                   [(labels, stats[field]) for labels, stats in endpoint_rows])

        return "\n".join(output) + "\n"
