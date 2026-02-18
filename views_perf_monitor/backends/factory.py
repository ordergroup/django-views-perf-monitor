from django.conf import settings
from django.utils.module_loading import import_string

from views_perf_monitor.backends import PerformanceMonitorBackend

DEFAULT_BACKEND = {
    "backend": "views_perf_monitor.backends.dummy.DummyBackend",
    "kwargs": {},
}


def get_performance_monitor_backend() -> PerformanceMonitorBackend:
    backend_conf = getattr(settings, "VIEWS_PERF_MONITOR_BACKEND", DEFAULT_BACKEND)
    backend_class = import_string(backend_conf["backend"])
    return backend_class(**backend_conf.get("kwargs", {}))
