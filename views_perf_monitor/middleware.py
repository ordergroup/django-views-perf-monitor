import logging
from collections.abc import Callable
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from views_perf_monitor.backends.factory import get_performance_monitor_backend
from views_perf_monitor.models import PerformanceRecord

logger = logging.getLogger(__name__)


def default_get_request_tags(request: HttpRequest) -> list[str]:
    if "/api" in request.path:
        return ["api"]
    if "/admin" in request.path:
        return ["admin"]
    return []


def default_get_request_id(request: HttpRequest) -> str:
    return str(uuid4())


DEFAULT_RECORD_UNTAGGED = True


def perf_middleware(get_response: Callable[[HttpRequest], HttpResponse]):
    backend = get_performance_monitor_backend()

    def middleware(request: HttpRequest):
        timestamp = datetime.now(tz=timezone.utc)
        start = perf_counter()

        response = get_response(request)

        duration = perf_counter() - start
        route = (
            "/" + request.resolver_match.route.lstrip("/")
            if request.resolver_match
            else request.path
        )

        try:
            request_tags_callable: Callable[[HttpRequest], list[str]] = getattr(
                settings,
                "VIEWS_PERF_REQUEST_TAGS_CALLABLE",
                default_get_request_tags,
            )
            request_tags = request_tags_callable(request)
        except Exception:
            logger.exception("failed to extract request tags")
            request_tags = []

        should_save = request_tags or getattr(
            settings, "VIEWS_PERF_RECORD_UNTAGGED", DEFAULT_RECORD_UNTAGGED
        )

        if not should_save:
            return response

        try:
            request_id_callable: Callable[[HttpRequest], str] = getattr(
                settings,
                "VIEWS_PERF_REQUEST_ID_CALLABLE",
                default_get_request_id,
            )
            request_id = request_id_callable(request)
        except Exception:
            logger.exception("failed to extract request id")
            request_id = str(uuid4())

        try:
            record = PerformanceRecord(
                timestamp=timestamp,
                duration=duration,
                route=route,
                status_code=response.status_code,
                method=request.method or "",
                tags=request_tags,
                request_id=request_id,
            )
            backend.save(record)
        except Exception:
            logger.exception("failed to save request to the perf backend")

        return response

    return middleware
