from collections import defaultdict

from views_perf_monitor.models import (
    PerformanceRecord,
    RouteStats,
    RouteTagStats,
    TagStats,
)


def all_stats(
    records: list[PerformanceRecord],
) -> tuple[list[TagStats], list[RouteStats]]:
    # name: [total_duration, count]
    route_stats: defaultdict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    tag_stats: defaultdict[str, list[float]] = defaultdict(lambda: [0.0, 0])

    for record in records:
        route_stats[record.route][0] += record.duration
        route_stats[record.route][1] += 1

        for tag in record.tags:
            tag_stats[tag][0] += record.duration
            tag_stats[tag][1] += 1
    tags_stats = sorted(
        [
            TagStats(tag=tag, avg=total / count, count=int(count))
            for tag, (total, count) in tag_stats.items()
        ],
        key=lambda r: r.avg,
        reverse=True,
    )
    routes_stats = sorted(
        [
            RouteStats(route=route, avg=total / count, count=int(count))
            for route, (total, count) in route_stats.items()
        ],
        key=lambda r: r.avg,
        reverse=True,
    )

    return tags_stats, routes_stats


def route_tag_breakdown(
    records: list[PerformanceRecord],
) -> dict[str, dict[str, RouteTagStats]]:
    # route -> tag -> [total, count]
    stats: defaultdict[str, defaultdict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0])
    )
    for record in records:
        for tag in record.tags:
            stats[record.route][tag][0] += record.duration
            stats[record.route][tag][1] += 1

    return {
        route: {
            tag: RouteTagStats(avg=total / count, count=int(count))
            for tag, (total, count) in tags.items()
        }
        for route, tags in stats.items()
    }


def weighted_avg(stats) -> tuple[int, float]:
    total_count = sum(r.count for r in stats)
    total_avg = sum(r.avg * r.count for r in stats) / total_count if total_count else 0
    return total_count, total_avg
