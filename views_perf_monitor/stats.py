import math
from collections import defaultdict

from views_perf_monitor.models import (
    PerformanceRecord,
    RouteStats,
    RouteTagStats,
    StatusCodeStats,
    TagStats,
)


def _percentile(sorted_durations: list[float], p: float) -> float:
    """Nearest-rank percentile on a pre-sorted list."""
    if not sorted_durations:
        return 0.0
    idx = max(0, math.ceil(p / 100 * len(sorted_durations)) - 1)
    return sorted_durations[idx]


def all_stats(
    records: list[PerformanceRecord],
) -> tuple[list[TagStats], list[RouteStats]]:
    # name: [total_duration, count, [durations], error_count]
    route_stats: defaultdict[str, list] = defaultdict(lambda: [0.0, 0, [], 0])
    tag_stats: defaultdict[str, list] = defaultdict(lambda: [0.0, 0, []])

    for record in records:
        route_stats[record.route][0] += record.duration
        route_stats[record.route][1] += 1
        route_stats[record.route][2].append(record.duration)
        if record.status_code >= 400:
            route_stats[record.route][3] += 1

        for tag in record.tags:
            tag_stats[tag][0] += record.duration
            tag_stats[tag][1] += 1
            tag_stats[tag][2].append(record.duration)

    tags_stats = sorted(
        [
            TagStats(
                tag=tag,
                avg=total / count,
                count=int(count),
                p95=_percentile(sorted(durations), 95),
                p99=_percentile(sorted(durations), 99),
            )
            for tag, (total, count, durations) in tag_stats.items()
        ],
        key=lambda r: r.avg,
        reverse=True,
    )
    routes_stats = sorted(
        [
            RouteStats(
                route=route,
                avg=total / count,
                count=int(count),
                p95=_percentile(sorted(durations), 95),
                p99=_percentile(sorted(durations), 99),
                error_count=int(errors),
                error_rate=round(errors / count * 100, 1) if count else 0.0,
                min_duration=min(durations) if durations else 0.0,
                max_duration=max(durations) if durations else 0.0,
            )
            for route, (total, count, durations, errors) in route_stats.items()
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


def request_trend(
    records: list[PerformanceRecord],
) -> dict[str, int]:
    """Returns an ordered dict of ISO hour string -> request count."""
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        bucket = record.timestamp.strftime("%Y-%m-%dT%H:00")
        counts[bucket] += 1
    return dict(sorted(counts.items()))


def status_code_stats(records: list[PerformanceRecord]) -> list[StatusCodeStats]:
    counts: defaultdict[int, int] = defaultdict(int)
    for record in records:
        counts[record.status_code] += 1

    def _group(code: int) -> str:
        if 200 <= code < 300:
            return "2xx"
        if 300 <= code < 400:
            return "3xx"
        if 400 <= code < 500:
            return "4xx"
        if 500 <= code < 600:
            return "5xx"
        return "other"

    return sorted(
        [
            StatusCodeStats(status_code=code, count=count, group=_group(code))
            for code, count in counts.items()
        ],
        key=lambda s: s.status_code,
    )


def weighted_avg(stats) -> tuple[int, float]:
    total_count = sum(r.count for r in stats)
    total_avg = sum(r.avg * r.count for r in stats) / total_count if total_count else 0
    return total_count, total_avg
