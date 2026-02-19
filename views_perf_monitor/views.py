import json
from contextlib import suppress
from datetime import datetime, timezone
from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.core.paginator import Paginator
from django.http import HttpRequest
from django.template.response import TemplateResponse

from views_perf_monitor.backends import PerformanceRecordQueryBuilder
from views_perf_monitor.backends.factory import get_performance_monitor_backend
from views_perf_monitor.models import RouteStats, RouteTagStats, TagStats
from views_perf_monitor.stats import (
    all_stats,
    request_trend,
    route_tag_breakdown,
    status_code_stats,
    weighted_avg,
)

VALID_SORT_FIELDS = {"avg", "count"}


def dashboard_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    sort = request.GET.get("sort", "avg")
    if sort not in VALID_SORT_FIELDS:
        sort = "avg"

    since, until = _parse_date_range(request)
    backend = get_performance_monitor_backend()
    query = PerformanceRecordQueryBuilder.all().for_date_range(since, until)
    records = backend.fetch(query)

    tags_stats, routes_stats = all_stats(records)
    route_tag_breakdown_stats = route_tag_breakdown(records)
    status_stats = status_code_stats(records)
    trend_data = request_trend(records)

    tags_stats = sorted(tags_stats, key=lambda r: getattr(r, sort, 0), reverse=True)
    routes_stats = sorted(routes_stats, key=lambda r: getattr(r, sort, 0), reverse=True)

    tags_total_count, tags_total_avg = weighted_avg(tags_stats)
    routes_total_count, routes_total_avg = weighted_avg(routes_stats)

    all_tags = backend.get_all_tags()

    context = {
        **site.each_context(request),
        "title": "Django Views Performance Monitor",
        "tags_stats": tags_stats,
        "routes_stats": routes_stats,
        "sort": sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "tags_chart_data": _build_tags_chart_data(tags_stats),
        "routes_chart_data": _build_routes_chart_data(routes_stats),
        "tags_total_count": tags_total_count,
        "tags_total_avg": tags_total_avg,
        "routes_total_count": routes_total_count,
        "routes_total_avg": routes_total_avg,
        "all_tags": all_tags,
        "route_tag_chart_data": _build_route_tag_chart_data(
            routes_stats, route_tag_breakdown_stats
        ),
        "status_stats": status_stats,
        "status_chart_data": _build_status_chart_data(status_stats),
        "trend_chart_data": json.dumps(trend_data) if trend_data else "",
    }
    return TemplateResponse(request, "views_perf_monitor/dashboard.html", context)


VALID_BREAKDOWN_SORT_FIELDS = {
    "timestamp",
    "route",
    "method",
    "status_code",
    "duration",
}


def tag_breakdown_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    backend = get_performance_monitor_backend()
    tag = request.GET.get("tag", "")
    sort = request.GET.get("sort", "timestamp")

    route_filter = request.GET.get("route", "").strip()
    if sort not in VALID_BREAKDOWN_SORT_FIELDS:
        sort = "timestamp"

    since, until = _parse_date_range(request)

    query = (
        PerformanceRecordQueryBuilder.for_tag(tag)
        .filter_by_route(route_filter)
        .for_date_range(since, until)
        .order_by(sort)
    )

    records = backend.fetch(query)
    tag_status_stats = status_code_stats(records)
    paginator = Paginator(records, 50)
    page = paginator.get_page(request.GET.get("page", 1))

    pagination_params = urlencode({k: v for k, v in request.GET.items() if k != "page"})
    context = {
        **site.each_context(request),
        "title": f"Tag: {tag}",
        "tag": tag,
        "status_stats": tag_status_stats,
        "page_obj": page,
        "page_range": paginator.get_elided_page_range(
            page.number, on_each_side=2, on_ends=1
        ),
        "ellipsis": Paginator.ELLIPSIS,
        "pagination_params": pagination_params,
        "sort": sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "route_filter": route_filter,
        "available_routes": backend.get_all_routes(),
    }
    return TemplateResponse(request, "views_perf_monitor/tag_breakdown.html", context)


def route_breakdown_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    backend = get_performance_monitor_backend()
    route = request.GET.get("route", "")
    sort = request.GET.get("sort", "timestamp")
    if sort not in VALID_BREAKDOWN_SORT_FIELDS:
        sort = "timestamp"

    tag_filter = request.GET.get("tag", "").strip()
    since, until = _parse_date_range(request)

    query = (
        PerformanceRecordQueryBuilder.for_route(route)
        .filter_by_tag(tag_filter)
        .for_date_range(since, until)
        .order_by(sort)
    )
    records = backend.fetch(query)
    paginator = Paginator(records, 50)
    page = paginator.get_page(request.GET.get("page", 1))

    pagination_params = urlencode({k: v for k, v in request.GET.items() if k != "page"})
    context = {
        **site.each_context(request),
        "title": f"Route: {route}",
        "route": route,
        "page_obj": page,
        "page_range": paginator.get_elided_page_range(
            page.number, on_each_side=2, on_ends=1
        ),
        "ellipsis": Paginator.ELLIPSIS,
        "pagination_params": pagination_params,
        "sort": sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "tag_filter": tag_filter,
        "available_tags": backend.get_all_tags(),
    }
    return TemplateResponse(request, "views_perf_monitor/route_breakdown.html", context)


def _parse_date_range(request: HttpRequest) -> tuple[datetime | None, datetime | None]:
    since = until = None
    with suppress(KeyError, ValueError):
        since = datetime.fromisoformat(request.GET["since"]).replace(
            tzinfo=timezone.utc
        )
    with suppress(KeyError, ValueError):
        until = datetime.fromisoformat(request.GET["until"]).replace(
            tzinfo=timezone.utc
        )
    return since, until


def _build_tags_chart_data(stats: list[TagStats]) -> str:
    return json.dumps(
        [{"tag": r.tag, "avg": round(r.avg, 4), "count": r.count} for r in stats]
    )


def _build_routes_chart_data(stats: list[RouteStats]) -> str:
    return json.dumps(
        [{"route": r.route, "avg": round(r.avg, 4), "count": r.count} for r in stats]
    )


def _build_status_chart_data(stats) -> str:
    return json.dumps(
        [
            {"status_code": s.status_code, "count": s.count, "group": s.group}
            for s in stats
        ]
    )


def _build_route_tag_chart_data(
    routes_stats: list[RouteStats], breakdown: dict[str, dict[str, RouteTagStats]]
) -> str:
    all_tags = sorted({tag for tag_map in breakdown.values() for tag in tag_map})
    route_order = [r.route for r in routes_stats]
    return json.dumps(
        {
            "routes": route_order,
            "tags": all_tags,
            "datasets": [
                {
                    "tag": tag,
                    "avgs": [
                        round(s.avg, 4)
                        if (s := breakdown.get(route, {}).get(tag)) is not None
                        else None
                        for route in route_order
                    ],
                    "counts": [
                        s.count
                        if (s := breakdown.get(route, {}).get(tag)) is not None
                        else None
                        for route in route_order
                    ],
                }
                for tag in all_tags
            ],
        }
    )
