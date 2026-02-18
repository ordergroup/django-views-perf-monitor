from views_perf_monitor.backends import PerformanceMonitorBackend
from views_perf_monitor.models import PerformanceRecord


class DummyBackend(PerformanceMonitorBackend):
    def save(self, record: PerformanceRecord):
        pass

    def get_by_tag(self, tag: str) -> list[PerformanceRecord]:
        return []

    def get_all_tags(self) -> list[str]:
        return []

    def get_all_routes(self) -> list[str]:
        return []

    def get_by_route(self, route: str) -> list[PerformanceRecord]:
        return []
