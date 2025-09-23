from collections import defaultdict
import time
from typing import Dict, Any

class KeyStats:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0
        self.last_used = 0.0
        self.last_success = 0.0
        self.last_failure = 0.0
        self.consecutive_failures = 0
        self.rate_limit_hits = 0
        self.is_healthy = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_response_time": self.avg_response_time,
            "last_used": self.last_used,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "consecutive_failures": self.consecutive_failures,
            "rate_limit_hits": self.rate_limit_hits,
            "is_healthy": self.is_healthy,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KeyStats':
        stats = KeyStats()
        stats.total_requests = data.get("total_requests", 0)
        stats.successful_requests = data.get("successful_requests", 0)
        stats.failed_requests = data.get("failed_requests", 0)
        stats.avg_response_time = data.get("avg_response_time", 0.0)
        stats.last_used = data.get("last_used", 0.0)
        stats.last_success = data.get("last_success", 0.0)
        stats.last_failure = data.get("last_failure", 0.0)
        stats.consecutive_failures = data.get("consecutive_failures", 0)
        stats.rate_limit_hits = data.get("rate_limit_hits", 0)
        stats.is_healthy = data.get("is_healthy", True)
        return stats

class EndpointStats:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.avg_response_time = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_response_time": self.avg_response_time,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'EndpointStats':
        stats = EndpointStats()
        stats.total_requests = data.get("total_requests", 0)
        stats.successful_requests = data.get("successful_requests", 0)
        stats.failed_requests = data.get("failed_requests", 0)
        stats.avg_response_time = data.get("avg_response_time", 0.0)
        return stats

class RotatorMetrics:
    def __init__(self):
        self.key_stats: Dict[str, KeyStats] = defaultdict(KeyStats)
        self.endpoint_stats: Dict[str, EndpointStats] = defaultdict(EndpointStats)
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = time.time()

    def record_request(self, key: str, endpoint: str, success: bool, response_time: float, is_rate_limited: bool = False):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.key_stats[key].successful_requests += 1
            self.key_stats[key].last_success = time.time()
            self.key_stats[key].consecutive_failures = 0
        else:
            self.failed_requests += 1
            self.key_stats[key].failed_requests += 1
            self.key_stats[key].last_failure = time.time()
            self.key_stats[key].consecutive_failures += 1

        self.key_stats[key].total_requests += 1
        self.key_stats[key].avg_response_time = (self.key_stats[key].avg_response_time * (self.key_stats[key].total_requests - 1) + response_time) / self.key_stats[key].total_requests if self.key_stats[key].total_requests > 0 else response_time
        self.key_stats[key].last_used = time.time()
        if is_rate_limited:
            self.key_stats[key].rate_limit_hits += 1

        self.endpoint_stats[endpoint].total_requests += 1
        if success:
            self.endpoint_stats[endpoint].successful_requests += 1
        else:
            self.endpoint_stats[endpoint].failed_requests += 1
        self.endpoint_stats[endpoint].avg_response_time = (self.endpoint_stats[endpoint].avg_response_time * (self.endpoint_stats[endpoint].total_requests - 1) + response_time) / self.endpoint_stats[endpoint].total_requests if self.endpoint_stats[endpoint].total_requests > 0 else response_time

    def get_metrics(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "uptime_seconds": uptime,
            "key_stats": {k: v.to_dict() for k, v in self.key_stats.items()},
            "endpoint_stats": {k: v.to_dict() for k, v in self.endpoint_stats.items()},
        }

    def export_prometheus(self) -> str:
        # Basic Prometheus format export
        output = []
        output.append(f"# HELP rotator_total_requests Total requests processed by the rotator.")
        output.append(f"# TYPE rotator_total_requests counter")
        output.append(f"rotator_total_requests {self.total_requests}")

        output.append(f"# HELP rotator_successful_requests Total successful requests processed by the rotator.")
        output.append(f"# TYPE rotator_successful_requests counter")
        output.append(f"rotator_successful_requests {self.successful_requests}")

        output.append(f"# HELP rotator_failed_requests Total failed requests processed by the rotator.")
        output.append(f"# TYPE rotator_failed_requests counter")
        output.append(f"rotator_failed_requests {self.failed_requests}")

        for key, stats in self.key_stats.items():
            key_label = key[:8] + "..." # Truncate key for labels
            output.append(f"# HELP rotator_key_total_requests Total requests for API key.")
            output.append(f"# TYPE rotator_key_total_requests counter")
            output.append(f"rotator_key_total_requests{{key=\"{key_label}\"}} {stats.total_requests}")
            output.append(f"rotator_key_successful_requests{{key=\"{key_label}\"}} {stats.successful_requests}")
            output.append(f"rotator_key_failed_requests{{key=\"{key_label}\"}} {stats.failed_requests}")
            output.append(f"rotator_key_avg_response_time_seconds{{key=\"{key_label}\"}} {stats.avg_response_time}")
            output.append(f"rotator_key_rate_limit_hits_total{{key=\"{key_label}\"}} {stats.rate_limit_hits}")
            output.append(f"rotator_key_is_healthy{{key=\"{key_label}\"}} {1 if stats.is_healthy else 0}")

        for endpoint, stats in self.endpoint_stats.items():
            output.append(f"# HELP rotator_endpoint_total_requests Total requests for endpoint.")
            output.append(f"# TYPE rotator_endpoint_total_requests counter")
            output.append(f"rotator_endpoint_total_requests{{endpoint=\"{endpoint}\"}} {stats.total_requests}")
            output.append(f"rotator_endpoint_successful_requests{{endpoint=\"{endpoint}\"}} {stats.successful_requests}")
            output.append(f"rotator_endpoint_failed_requests{{endpoint=\"{endpoint}\"}} {stats.failed_requests}")
            output.append(f"rotator_endpoint_avg_response_time_seconds{{endpoint=\"{endpoint}\"}} {stats.avg_response_time}")

        return "\n".join(output)


