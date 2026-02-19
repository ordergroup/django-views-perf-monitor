import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TagStats:
    tag: str
    avg: float
    count: int


@dataclass
class RouteStats:
    route: str
    avg: float
    count: int


@dataclass
class RouteTagStats:
    avg: float
    count: int


@dataclass
class PerformanceRecord:
    request_id: str
    timestamp: datetime
    duration: int | float
    route: str
    status_code: int
    method: str
    tags: list[str]

    def model_dump_json(self) -> str:
        data = {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "duration": self.duration,
            "route": self.route,
            "status_code": self.status_code,
            "method": self.method,
            "tags": self.tags,
        }
        return json.dumps(data)

    @classmethod
    def model_validate_json(cls, raw: str | bytes) -> "PerformanceRecord":
        data = json.loads(raw)
        return cls(
            request_id=data["request_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration=data["duration"],
            route=data["route"],
            status_code=data["status_code"],
            method=data["method"],
            tags=data["tags"],
        )

    @classmethod
    def from_raw_records(cls, raw_records: list[Any]) -> "list[PerformanceRecord]":
        results = []
        for raw_record in raw_records:
            if not raw_record:
                continue

            with suppress(Exception):
                results.append(cls.model_validate_json(raw_record))

        return results
