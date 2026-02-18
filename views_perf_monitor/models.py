from contextlib import suppress
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError


class TagStats(BaseModel):
    tag: str
    avg: float
    count: int


class RouteStats(BaseModel):
    route: str
    avg: float
    count: int


class RouteTagStats(BaseModel):
    avg: float
    count: int


class PerformanceRecord(BaseModel):
    request_id: str
    timestamp: datetime
    duration: int | float
    route: str
    status_code: int
    method: str
    tags: list[str]

    @classmethod
    def from_raw_records(cls, raw_records: list[Any]) -> "list[PerformanceRecord]":
        results = []
        for raw_record in raw_records:
            if not raw_record:
                continue

            with suppress(ValidationError):
                results.append(cls.model_validate_json(raw_record))

        return results
