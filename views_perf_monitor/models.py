from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TagStats:
    tag: str
    avg: float
    count: int
    p95: float = 0.0
    p99: float = 0.0
    min_duration: float = 0.0
    max_duration: float = 0.0


@dataclass
class RouteStats:
    route: str
    avg: float
    count: int
    p95: float = 0.0
    p99: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0  # percentage 0-100
    min_duration: float = 0.0
    max_duration: float = 0.0


@dataclass
class RouteTagStats:
    avg: float
    count: int


@dataclass
class StatusCodeStats:
    status_code: int
    count: int
    group: str  # "2xx", "3xx", "4xx", "5xx", "other"


@dataclass
class PerformanceRecord:
    request_id: str
    timestamp: datetime
    duration: int | float
    route: str
    status_code: int
    method: str
    tags: list[str]

    @classmethod
    def from_dict_list(cls, data: list[dict]) -> "list[PerformanceRecord]":
        results = []
        for item in data:
            record = PerformanceRecord.from_dict(item)
            if not record:
                continue

            results.append(record)

        return results

    @classmethod
    def from_dict(cls, item: dict) -> "PerformanceRecord | None":
        with suppress(KeyError, ValueError, TypeError):
            return cls(
                request_id=item["request_id"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
                duration=item["duration"],
                route=item["route"],
                status_code=item["status_code"],
                method=item["method"],
                tags=item["tags"],
            )

    def model_dump(self) -> dict:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "duration": self.duration,
            "route": self.route,
            "status_code": self.status_code,
            "method": self.method,
            "tags": self.tags,
        }
