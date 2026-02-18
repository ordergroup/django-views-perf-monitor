from views_perf_monitor.backends import (
    PerformanceMonitorBackend,
    PerformanceRecordQueryBuilder,
)
from views_perf_monitor.models import PerformanceRecord


class DummyBackend(PerformanceMonitorBackend):
    def save(self, record: PerformanceRecord):
        pass

    def get_all_tags(self) -> list[str]:
        return []

    def get_all_routes(self) -> list[str]:
        return []

    def fetch(self, query: PerformanceRecordQueryBuilder) -> list[PerformanceRecord]:
        return []
