from abc import ABC, abstractmethod
from datetime import datetime

from views_perf_monitor.models import (
    PerformanceRecord,
    RouteStats,
    RouteTagStats,
    StatusCodeStats,
    TagStats,
)


class PerformanceRecordQueryBuilder:
    def __init__(self, tag: str | None = None, route: str | None = None):
        self.tag = tag
        self.route = route
        self.since: datetime | None = None
        self.until: datetime | None = None
        self.order_by_field: str | None = None
        self.order_direction: str = "desc"  # 'asc' or 'desc'
        self.limit_records: int | None = None

    @classmethod
    def for_tag(cls, tag: str) -> "PerformanceRecordTagQueryBuilder":
        return PerformanceRecordTagQueryBuilder(tag=tag)

    @classmethod
    def for_route(cls, route: str) -> "PerformanceRecordRouteQueryBuilder":
        return PerformanceRecordRouteQueryBuilder(route=route)

    @classmethod
    def all(cls) -> "PerformanceRecordQueryBuilder":
        return cls()

    def for_date_range(
        self, since: datetime | None, until: datetime | None
    ) -> "PerformanceRecordQueryBuilder":
        self.since = since
        self.until = until
        return self

    def order_by(
        self, field: str, direction: str = "desc"
    ) -> "PerformanceRecordQueryBuilder":
        self.order_by_field = field
        self.order_direction = direction if direction in ("asc", "desc") else "desc"
        return self

    def limit(self, limit: int | None) -> "PerformanceRecordQueryBuilder":
        self.limit_records = limit
        return self


class PerformanceRecordTagQueryBuilder(PerformanceRecordQueryBuilder):
    def filter_by_route(self, route: str) -> "PerformanceRecordTagQueryBuilder":
        self.route_filter = route
        return self

    def filter_by_status_code(
        self, status_code: int
    ) -> "PerformanceRecordTagQueryBuilder":
        self.status_code_filter = status_code
        return self


class PerformanceRecordRouteQueryBuilder(PerformanceRecordQueryBuilder):
    def filter_by_tag(self, tag: str) -> "PerformanceRecordRouteQueryBuilder":
        self.tag_filter = tag
        return self

    def filter_by_status_code(
        self, status_code: int
    ) -> "PerformanceRecordRouteQueryBuilder":
        self.status_code_filter = status_code
        return self


class PerformanceMonitorBackend(ABC):
    @abstractmethod
    def save(self, record: PerformanceRecord): ...

    @abstractmethod
    def fetch(
        self, query: PerformanceRecordQueryBuilder
    ) -> list[PerformanceRecord]: ...

    @abstractmethod
    def get_all_tags(self) -> list[str]: ...

    @abstractmethod
    def get_all_routes(self) -> list[str]: ...

    @abstractmethod
    def get_tags_stats(self, query: PerformanceRecordQueryBuilder) -> list[TagStats]:
        """Get tag statistics."""

    @abstractmethod
    def get_routes_stats(
        self, query: PerformanceRecordQueryBuilder
    ) -> list[RouteStats]:
        """Get route statistics."""

    @abstractmethod
    def weighted_avg(self, query: PerformanceRecordQueryBuilder) -> tuple[int, float]:
        """
        Calculate weighted average from route stats.

        Returns:
            tuple: (total_count, weighted_avg)
        """

    @abstractmethod
    def route_tag_breakdown(
        self, query: PerformanceRecordQueryBuilder
    ) -> dict[str, dict[str, RouteTagStats]]:
        """Get route-tag performance breakdown."""

    @abstractmethod
    def request_trend(self, query: PerformanceRecordQueryBuilder) -> dict[str, int]:
        """Returns an ordered dict of ISO hour string -> request count."""

    @abstractmethod
    def status_code_stats(
        self, query: PerformanceRecordQueryBuilder
    ) -> list[StatusCodeStats]:
        """Get status code distribution."""

    @abstractmethod
    def is_recording_enabled(self) -> bool:
        """Check if recording is currently enabled."""

    @abstractmethod
    def enable_recording(self) -> None:
        """Enable recording of performance data."""

    @abstractmethod
    def disable_recording(self) -> None:
        """Disable recording of performance data."""

    @abstractmethod
    def clear_data(self) -> None:
        """Clear all performance data."""
