from abc import ABC, abstractmethod
from datetime import datetime

from views_perf_monitor.models import PerformanceRecord


class PerformanceRecordQueryBuilder:
    def __init__(self, tag: str | None = None, route: str | None = None):
        self.tag = tag
        self.route = route
        self.since: datetime | None = None
        self.until: datetime | None = None
        self.order_by_field: str | None = None

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

    def order_by(self, field: str) -> "PerformanceRecordQueryBuilder":
        self.order_by_field = field
        return self


class PerformanceRecordTagQueryBuilder(PerformanceRecordQueryBuilder):
    def filter_by_route(self, route: str) -> "PerformanceRecordTagQueryBuilder":
        self.route_filter = route
        return self


class PerformanceRecordRouteQueryBuilder(PerformanceRecordQueryBuilder):
    def filter_by_tag(self, tag: str) -> "PerformanceRecordRouteQueryBuilder":
        self.tag_filter = tag
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
