import json
from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_POST

from views_perf_monitor.backends import PerformanceRecordQueryBuilder
from views_perf_monitor.backends.factory import get_performance_monitor_backend
from views_perf_monitor.filters import (
    RouteBreakdownFilters,
    RouteTagBreakdownFilters,
    StatsFilters,
    TagBreakdownFilters,
)
from views_perf_monitor.models import RouteStats, RouteTagStats, TagStats
from views_perf_monitor.stats import (
    status_code_stats,
    weighted_avg,
)

REQUESTS_LIMIT = 100_000


def tags_stats_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    filters = StatsFilters.from_request(request)
    backend = get_performance_monitor_backend()
    query = PerformanceRecordQueryBuilder.all().for_date_range(
        filters.since, filters.until
    )
    tags_stats = backend.get_tags_stats(query)

    tags_stats = sorted(
        tags_stats, key=lambda r: getattr(r, filters.sort, 0), reverse=True
    )
    tags_total_count, tags_total_avg = weighted_avg(tags_stats)

    # Get data time range if no filters applied
    data_since, data_until = (None, None)
    if (
        not filters.since
        and not filters.until
        and hasattr(backend, "get_data_time_range")
    ):
        data_since, data_until = backend.get_data_time_range()

    context = {
        **site.each_context(request),
        "title": "Tags Performance Statistics",
        "tags_stats": tags_stats,
        "tags_chart_data": _build_tags_chart_data(tags_stats),
        "tags_total_count": tags_total_count,
        "tags_total_avg": tags_total_avg,
        "sort": filters.sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "data_since": data_since,
        "data_until": data_until,
    }

    return TemplateResponse(request, "views_perf_monitor/tags_stats.html", context)


def routes_stats_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    filters = StatsFilters.from_request(request)
    backend = get_performance_monitor_backend()

    # Get tag filter from query params
    tag = request.GET.get("tag", "")

    # Get all available tags for the selector
    available_tags = backend.get_all_tags()

    # Build query with optional tag filter
    if tag:
        query = PerformanceRecordQueryBuilder.for_tag(tag).for_date_range(
            filters.since, filters.until
        )
        title = f"Routes for Tag: {tag}"
    else:
        query = PerformanceRecordQueryBuilder.all().for_date_range(
            filters.since, filters.until
        )
        title = "Routes Performance Statistics"

    routes_stats = backend.get_routes_stats(query)

    routes_stats = sorted(
        routes_stats, key=lambda r: getattr(r, filters.sort, 0), reverse=True
    )
    routes_total_count, routes_total_avg = weighted_avg(routes_stats)

    data_since, data_until = (None, None)
    if (
        not filters.since
        and not filters.until
        and hasattr(backend, "get_data_time_range")
    ):
        data_since, data_until = backend.get_data_time_range()

    context = {
        **site.each_context(request),
        "title": title,
        "tag": tag,
        "available_tags": available_tags,
        "routes_stats": routes_stats,
        "routes_chart_data": _build_routes_chart_data(routes_stats),
        "routes_total_count": routes_total_count,
        "routes_total_avg": routes_total_avg,
        "sort": filters.sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "data_since": data_since,
        "data_until": data_until,
    }

    return TemplateResponse(request, "views_perf_monitor/routes_stats.html", context)


def route_x_tag_breakdown_view(
    request: HttpRequest, site: AdminSite
) -> TemplateResponse:
    filters = RouteTagBreakdownFilters.from_request(request)
    backend = get_performance_monitor_backend()
    query = PerformanceRecordQueryBuilder.all().for_date_range(
        filters.since, filters.until
    )
    route_tag_breakdown_stats = backend.route_tag_breakdown(query)

    context = {
        **site.each_context(request),
        "title": "Django Views Performance Monitor",
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "route_tag_chart_data": _build_route_tag_chart_data(route_tag_breakdown_stats),
        "exclude_untagged": filters.exclude_untagged,
    }

    return TemplateResponse(
        request, "views_perf_monitor/route_tag_breakdown.html", context
    )


def dashboard_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    backend = get_performance_monitor_backend()

    query = PerformanceRecordQueryBuilder.all()

    status_stats = backend.status_code_stats(query)
    trend_data = backend.request_trend(query)
    tags_stats = backend.get_tags_stats(query)

    # Sort tags by count (descending)
    tags_stats = sorted(tags_stats, key=lambda t: t.count, reverse=True)

    # Calculate total count for percentage calculations
    routes_total_count = sum(stat.count for stat in status_stats)
    tags_total_count = sum(stat.count for stat in tags_stats)

    # Check recording status
    recording_enabled = backend.is_recording_enabled()

    context = {
        **site.each_context(request),
        "title": "Django Views Performance Monitor",
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "status_stats": status_stats,
        "status_chart_data": _build_status_chart_data(status_stats),
        "trend_chart_data": json.dumps(trend_data) if trend_data else "",
        "routes_total_count": routes_total_count,
        "tags_stats": tags_stats,
        "tags_chart_data": _build_tags_chart_data(tags_stats),
        "tags_total_count": tags_total_count,
        "recording_enabled": recording_enabled,
    }

    return TemplateResponse(request, "views_perf_monitor/dashboard.html", context)


@require_POST
def toggle_recording_view(request: HttpRequest, site: AdminSite) -> JsonResponse:
    """Toggle recording on/off."""
    backend = get_performance_monitor_backend()

    action = request.POST.get("action")

    if action == "enable":
        backend.enable_recording()
        enabled = True
    elif action == "disable":
        backend.disable_recording()
        enabled = False
    else:
        enabled = backend.is_recording_enabled()

    return JsonResponse({"recording_enabled": enabled})


@require_POST
def clear_data_view(request: HttpRequest, site: AdminSite) -> JsonResponse:
    """Clear all performance data."""
    backend = get_performance_monitor_backend()

    try:
        backend.clear_data()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def tag_breakdown_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    backend = get_performance_monitor_backend()
    filters = TagBreakdownFilters.from_request(request)

    query = (
        PerformanceRecordQueryBuilder.for_tag(filters.tag)
        .filter_by_route(filters.route)
        .for_date_range(filters.since, filters.until)
        .limit(REQUESTS_LIMIT)
        .order_by(filters.sort, filters.order)
    )

    records = backend.fetch(query)
    tag_status_stats = status_code_stats(records)

    # we do filtering in view to preserve status code counts
    if filters.status_code:
        records = [
            record for record in records if record.status_code == filters.status_code
        ]

    paginator = Paginator(records, 50)
    page = paginator.get_page(request.GET.get("page", 1))
    pagination_params = urlencode({k: v for k, v in request.GET.items() if k != "page"})

    context = {
        **site.each_context(request),
        "title": f"Tag: {filters.tag}",
        "tag": filters.tag,
        "status_stats": tag_status_stats,
        "page_obj": page,
        "page_range": paginator.get_elided_page_range(
            page.number, on_each_side=2, on_ends=1
        ),
        "ellipsis": Paginator.ELLIPSIS,
        "pagination_params": pagination_params,
        "sort": filters.sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "route_filter": filters.route,
        "status_code_filter": str(filters.status_code) if filters.status_code else "",
        "available_routes": backend.get_all_routes(),
        "requests_limit": f"{REQUESTS_LIMIT:,}",
        "order": filters.order,
    }

    return TemplateResponse(request, "views_perf_monitor/tag_breakdown.html", context)


def route_breakdown_view(request: HttpRequest, site: AdminSite) -> TemplateResponse:
    backend = get_performance_monitor_backend()
    filters = RouteBreakdownFilters.from_request(request)

    query = (
        PerformanceRecordQueryBuilder.for_route(filters.route)
        .filter_by_tag(filters.tag)
        .for_date_range(filters.since, filters.until)
        .order_by(filters.sort, filters.order)
    )

    records = backend.fetch(query)

    route_status_stats = status_code_stats(records)
    # we do filtering in view to preserve status code counts
    if filters.status_code:
        records = [
            record for record in records if record.status_code == filters.status_code
        ]

    paginator = Paginator(records, 50)
    page = paginator.get_page(request.GET.get("page", 1))
    pagination_params = urlencode({k: v for k, v in request.GET.items() if k != "page"})

    context = {
        **site.each_context(request),
        "title": f"Route: {filters.route}",
        "route": filters.route,
        "status_stats": route_status_stats,
        "page_obj": page,
        "page_range": paginator.get_elided_page_range(
            page.number, on_each_side=2, on_ends=1
        ),
        "ellipsis": Paginator.ELLIPSIS,
        "pagination_params": pagination_params,
        "sort": filters.sort,
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "tag_filter": filters.tag,
        "status_code_filter": str(filters.status_code) if filters.status_code else "",
        "available_tags": backend.get_all_tags(),
        "requests_limit": f"{REQUESTS_LIMIT:,}",
        "order": filters.order,
    }

    return TemplateResponse(request, "views_perf_monitor/route_breakdown.html", context)


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


def _build_route_tag_chart_data(breakdown: dict[str, dict[str, RouteTagStats]]) -> str:
    all_tags = sorted({tag for tag_map in breakdown.values() for tag in tag_map})
    route_order = sorted(breakdown.keys())
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
