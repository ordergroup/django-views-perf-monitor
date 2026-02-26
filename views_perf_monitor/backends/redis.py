import hashlib
import json
import logging
import math
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone

from redis import Redis

from views_perf_monitor.backends import (
    PerformanceMonitorBackend,
    PerformanceRecordQueryBuilder,
)
from views_perf_monitor.models import (
    PerformanceRecord,
    RouteStats,
    RouteTagStats,
    StatusCodeStats,
    TagStats,
)

logger = logging.getLogger(__name__)

# Stream keys
MAIN_STREAM = "perf:stream"  # Main stream of all performance records
TAG_STREAM_PREFIX = "perf:tag_stream:"  # One stream per tag
ROUTE_STREAM_PREFIX = "perf:route_stream:"  # One stream per route

# Index keys (still using sets for quick lookups)
TAG_INDEX_KEY = "perf:tags"
ROUTE_INDEX_KEY = "perf:routes"

# Aggregation keys (for fast statistics)
STATS_ROUTE_PREFIX = "perf:stats:route:"  # Hash per route
STATS_TAG_PREFIX = "perf:stats:tag:"  # Hash per tag
STATS_ROUTE_TAG_PREFIX = "perf:stats:route_tag:"  # Hash per route-tag combo
STATS_GLOBAL = "perf:stats:global"  # Global statistics
HOURLY_COUNTS_HASH = "perf:hourly_counts"  # Hash: hour_bucket -> count
STATUS_CODE_COUNTS_HASH = "perf:status_code_counts"  # Hash: status_code -> count

# Cache keys
CACHE_PREFIX = "perf:cache:"  # Query result cache

# Control keys
RECORDING_ENABLED_KEY = "perf:recording_enabled"  # Flag to enable/disable recording

DEFAULT_TTL_DAYS = 30
DEFAULT_MAX_STREAM_LENGTH = 1_000_000  # Keep last 1M entries
DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes


class RedisBackend(PerformanceMonitorBackend):
    """
    Performance monitoring backend using Redis Streams with incremental aggregation.

    Maintains pre-aggregated statistics for fast dashboard queries while keeping
    full detail records in streams for filtered/detailed views.
    """

    def __init__(
        self,
        redis_url: str,
        ttl_days: int = DEFAULT_TTL_DAYS,
        max_stream_length: int = DEFAULT_MAX_STREAM_LENGTH,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ):
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.ttl_days = ttl_days
        self.max_stream_length = max_stream_length
        self.cache_ttl_seconds = cache_ttl_seconds

        # Lua script for atomic min/max updates
        self.update_min_max_script = self.redis.register_script("""
            local key = KEYS[1]
            local value = tonumber(ARGV[1])

            local current_min = redis.call('HGET', key, 'min_duration')
            local current_max = redis.call('HGET', key, 'max_duration')

            if not current_min or tonumber(current_min) > value then
                redis.call('HSET', key, 'min_duration', value)
            end

            if not current_max or tonumber(current_max) < value then
                redis.call('HSET', key, 'max_duration', value)
            end
        """)

    def save(self, record: PerformanceRecord):
        """Save a performance record and update aggregate statistics."""
        # Check if recording is enabled
        if not self.is_recording_enabled():
            return

        data = {
            "request_id": record.request_id,
            "timestamp": record.timestamp.isoformat(),
            "duration": str(record.duration),
            "route": record.route,
            "status_code": str(record.status_code),
            "method": record.method,
            "tags": json.dumps(record.tags),
        }

        is_error = 1 if record.status_code >= 400 else 0
        hour_bucket = record.timestamp.strftime("%Y-%m-%dT%H:00")

        with self.redis.pipeline() as pipe:
            pipe.xadd(
                MAIN_STREAM, data, maxlen=self.max_stream_length, approximate=True
            )

            # Increment hourly count for request trend
            pipe.hincrby(HOURLY_COUNTS_HASH, hour_bucket, 1)

            # Increment status code count
            pipe.hincrby(STATUS_CODE_COUNTS_HASH, str(record.status_code), 1)

            pipe.hincrby(STATS_GLOBAL, "count", 1)
            pipe.hincrbyfloat(STATS_GLOBAL, "total_duration", record.duration)
            pipe.hincrby(STATS_GLOBAL, "error_count", is_error)

            route_stats_key = f"{STATS_ROUTE_PREFIX}{record.route}"
            pipe.hincrby(route_stats_key, "count", 1)
            pipe.hincrbyfloat(route_stats_key, "total_duration", record.duration)
            pipe.hincrby(route_stats_key, "error_count", is_error)

            # Update min/max using Lua script for atomic comparison
            self._update_min_max(pipe, route_stats_key, record.duration)

            if record.tags:
                pipe.sadd(TAG_INDEX_KEY, *record.tags)
                for tag in record.tags:
                    pipe.xadd(
                        f"{TAG_STREAM_PREFIX}{tag}",
                        data,
                        maxlen=self.max_stream_length,
                        approximate=True,
                    )
                    tag_stats_key = f"{STATS_TAG_PREFIX}{tag}"
                    pipe.hincrby(tag_stats_key, "count", 1)
                    pipe.hincrbyfloat(tag_stats_key, "total_duration", record.duration)
                    self._update_min_max(pipe, tag_stats_key, record.duration)

                    # Route-tag combination stats
                    route_tag_key = f"{STATS_ROUTE_TAG_PREFIX}{record.route}:{tag}"
                    pipe.hincrby(route_tag_key, "count", 1)
                    pipe.hincrbyfloat(route_tag_key, "total_duration", record.duration)

            pipe.sadd(ROUTE_INDEX_KEY, record.route)
            pipe.xadd(
                f"{ROUTE_STREAM_PREFIX}{record.route}",
                data,
                maxlen=self.max_stream_length,
                approximate=True,
            )

            pipe.execute()

    def _update_min_max(self, pipe, key: str, duration: float):
        """Update min/max duration for a stats key using Lua script."""
        self.update_min_max_script(keys=[key], args=[duration], client=pipe)

    def get_all_tags(self) -> list[str]:
        return sorted(self.redis.smembers(TAG_INDEX_KEY))

    def get_all_routes(self) -> list[str]:
        return sorted(self.redis.smembers(ROUTE_INDEX_KEY))

    def get_data_time_range(self) -> tuple[datetime | None, datetime | None]:
        """Get the time range of available data from the main stream."""
        # Get the first entry
        first_entries = self.redis.xrange(MAIN_STREAM, count=1)
        # Get the last entry
        last_entries = self.redis.xrevrange(MAIN_STREAM, count=1)

        first_time = None
        last_time = None

        if first_entries:
            first_time = (
                self._parse_stream_entries([first_entries[0]])[0].timestamp
                if first_entries
                else None
            )

        if last_entries:
            last_time = (
                self._parse_stream_entries([last_entries[0]])[0].timestamp
                if last_entries
                else None
            )

        return first_time, last_time

    def fetch(self, query: PerformanceRecordQueryBuilder) -> list[PerformanceRecord]:
        cache_key = self._get_cache_key("fetch", query)
        cached_records = self._get_cached_records(cache_key)
        if cached_records is not None:
            return cached_records

        if query.tag:
            stream_key = f"{TAG_STREAM_PREFIX}{query.tag}"
        elif query.route:
            stream_key = f"{ROUTE_STREAM_PREFIX}{query.route}"
        else:
            stream_key = MAIN_STREAM

        min_id = self._datetime_to_stream_id(query.since) if query.since else "-"
        max_id = self._datetime_to_stream_id(query.until) if query.until else "+"

        stream_entries = self.redis.xrevrange(
            stream_key,
            max_id,
            min_id,
            count=query.limit_records,
        )
        records = self._parse_stream_entries(stream_entries)

        if route_filter := getattr(query, "route_filter", None):
            records = [r for r in records if r.route == route_filter]

        if tag_filter := getattr(query, "tag_filter", None):
            records = [r for r in records if tag_filter in r.tags]

        if status_code_filter := getattr(query, "status_code_filter", None):
            records = [r for r in records if r.status_code == status_code_filter]

        if order_by := query.order_by_field:
            reverse = query.order_direction == "desc"
            records = sorted(
                records, key=lambda r: getattr(r, order_by), reverse=reverse
            )

        self._cache_result(cache_key, [r.model_dump() for r in records])
        return records

    def get_tags_stats(self, query: PerformanceRecordQueryBuilder) -> list[TagStats]:
        if query.since or query.until:
            records = self.fetch(query)
            return self._compute_tag_stats_from_records(records)
        else:
            return self._get_aggregated_tag_stats()

    def get_routes_stats(
        self, query: PerformanceRecordQueryBuilder
    ) -> list[RouteStats]:
        if query.tag and not query.since and not query.until:
            return self._get_aggregated_route_stats_for_tag(query.tag)

        elif query.since or query.until or query.tag or query.route:
            records = self.fetch(query)
            return self._compute_route_stats_from_records(records)
        # No filters, use fully aggregated stats
        else:
            return self._get_aggregated_route_stats()

    def weighted_avg(self, query: PerformanceRecordQueryBuilder) -> tuple[int, float]:
        """Calculate weighted average from route stats."""
        route_stats = self.route_stats(query)
        total_count = sum(r.count for r in route_stats)
        weighted_avg = (
            sum(r.avg * r.count for r in route_stats) / total_count
            if total_count
            else 0
        )
        return total_count, weighted_avg

    def route_tag_breakdown(
        self, query: PerformanceRecordQueryBuilder
    ) -> dict[str, dict[str, RouteTagStats]]:
        """Get route-tag performance breakdown using pre-aggregated data or records."""
        if query.since or query.until:
            records = self.fetch(query)
            return self._compute_route_tag_breakdown_from_records(records)
        else:
            return self._get_aggregated_route_tag_breakdown()

    def request_trend(self, query: PerformanceRecordQueryBuilder) -> dict[str, int]:
        """Returns an ordered dict of ISO hour string -> request count."""
        counts = self.redis.hgetall(HOURLY_COUNTS_HASH)
        # Convert values to int and sort by key
        return dict(sorted({k: int(v) for k, v in counts.items()}.items()))

    def status_code_stats(
        self, query: PerformanceRecordQueryBuilder
    ) -> list[StatusCodeStats]:
        """Get status code distribution from pre-aggregated data."""

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

        counts = self.redis.hgetall(STATUS_CODE_COUNTS_HASH)
        return sorted(
            [
                StatusCodeStats(
                    status_code=int(code), count=int(count), group=_group(int(code))
                )
                for code, count in counts.items()
            ],
            key=lambda s: s.status_code,
        )

    def _get_aggregated_tag_stats(self) -> list[TagStats]:
        """Get pre-aggregated tag statistics from Redis."""
        all_tags = self.get_all_tags()
        if not all_tags:
            return []

        tag_stats = []
        with self.redis.pipeline() as pipe:
            for tag in all_tags:
                pipe.hgetall(f"{STATS_TAG_PREFIX}{tag}")
            results = pipe.execute()

        for i, tag in enumerate(all_tags):
            stats_data = results[i]
            if stats_data:
                count = int(stats_data.get("count", 0))
                total_duration = float(stats_data.get("total_duration", 0))
                avg = total_duration / count if count > 0 else 0
                min_duration = float(stats_data.get("min_duration", 0))
                max_duration = float(stats_data.get("max_duration", 0))

                tag_stats.append(
                    TagStats(
                        tag=tag,
                        count=count,
                        avg=avg,
                        p95=0,
                        p99=0,
                        min_duration=min_duration,
                        max_duration=max_duration,
                    )
                )

        return tag_stats

    def _get_aggregated_route_stats(self) -> list[RouteStats]:
        """Get pre-aggregated route statistics from Redis."""
        all_routes = self.get_all_routes()
        route_stats = []

        with self.redis.pipeline() as pipe:
            for route in all_routes:
                pipe.hgetall(f"{STATS_ROUTE_PREFIX}{route}")
            results = pipe.execute()

        for i, route in enumerate(all_routes):
            stats_data = results[i]
            if stats_data:
                count = int(stats_data.get("count", 0))
                total_duration = float(stats_data.get("total_duration", 0))
                error_count = int(stats_data.get("error_count", 0))
                avg = total_duration / count if count > 0 else 0
                error_rate = round(error_count / count * 100, 2) if count > 0 else 0
                min_duration = float(stats_data.get("min_duration", 0))
                max_duration = float(stats_data.get("max_duration", 0))

                route_stats.append(
                    RouteStats(
                        route=route,
                        count=count,
                        avg=avg,
                        p95=0,
                        p99=0,
                        error_count=error_count,
                        error_rate=error_rate,
                        min_duration=min_duration,
                        max_duration=max_duration,
                    )
                )

        return route_stats

    def _get_aggregated_route_stats_for_tag(self, tag: str) -> list[RouteStats]:
        """Get route statistics filtered by a specific tag using pre-aggregated data."""
        all_routes = self.get_all_routes()
        route_stats = []

        with self.redis.pipeline() as pipe:
            for route in all_routes:
                pipe.hgetall(f"{STATS_ROUTE_TAG_PREFIX}{route}:{tag}")
            results = pipe.execute()

        for i, route in enumerate(all_routes):
            stats_data = results[i]
            if stats_data and stats_data.get("count"):
                count = int(stats_data.get("count", 0))
                total_duration = float(stats_data.get("total_duration", 0))
                avg = total_duration / count if count > 0 else 0

                route_stats.append(
                    RouteStats(
                        route=route,
                        count=count,
                        avg=avg,
                        p95=0,
                        p99=0,
                        error_count=0,
                        error_rate=0,
                        min_duration=0,
                        max_duration=0,
                    )
                )

        return route_stats

    def _get_aggregated_route_tag_breakdown(
        self,
    ) -> dict[str, dict[str, RouteTagStats]]:
        """Get pre-aggregated route-tag breakdown from Redis."""
        all_routes = self.get_all_routes()
        all_tags = self.get_all_tags()

        if not all_routes or not all_tags:
            return {}

        # Build list of all possible route-tag combinations
        route_tag_pairs = [(route, tag) for route in all_routes for tag in all_tags]

        # Fetch all route-tag stats in a single pipeline
        with self.redis.pipeline() as pipe:
            for route, tag in route_tag_pairs:
                pipe.hgetall(f"{STATS_ROUTE_TAG_PREFIX}{route}:{tag}")
            results = pipe.execute()

        # Build the breakdown dictionary
        breakdown: dict[str, dict[str, RouteTagStats]] = {}

        for i, (route, tag) in enumerate(route_tag_pairs):
            stats_data = results[i]
            if stats_data and stats_data.get("count"):
                count = int(stats_data.get("count", 0))
                total_duration = float(stats_data.get("total_duration", 0))
                avg = total_duration / count if count > 0 else 0

                if route not in breakdown:
                    breakdown[route] = {}

                breakdown[route][tag] = RouteTagStats(avg=avg, count=count)

        return breakdown

    def _compute_tag_stats_from_records(
        self, records: list[PerformanceRecord]
    ) -> list[TagStats]:
        """Compute tag statistics from a list of records."""
        # tag: [total_duration, count, [durations], min, max]
        tag_stats: defaultdict[str, list] = defaultdict(
            lambda: [0.0, 0, [], float("inf"), 0.0]
        )

        for record in records:
            for tag in record.tags:
                tag_stats[tag][0] += record.duration
                tag_stats[tag][1] += 1
                tag_stats[tag][2].append(record.duration)
                tag_stats[tag][3] = min(tag_stats[tag][3], record.duration)
                tag_stats[tag][4] = max(tag_stats[tag][4], record.duration)

        return sorted(
            [
                TagStats(
                    tag=tag,
                    count=count,
                    avg=total / count if count else 0,
                    p95=_percentile(sorted(durations), 95),
                    p99=_percentile(sorted(durations), 99),
                    min_duration=min_dur if min_dur != float("inf") else 0,
                    max_duration=max_dur,
                )
                for tag, (
                    total,
                    count,
                    durations,
                    min_dur,
                    max_dur,
                ) in tag_stats.items()
            ],
            key=lambda t: t.avg,
            reverse=True,
        )

    def _compute_route_stats_from_records(
        self, records: list[PerformanceRecord]
    ) -> list[RouteStats]:
        """Compute route statistics from a list of records."""
        # route: [total_duration, count, [durations], error_count, min, max]
        route_stats: defaultdict[str, list] = defaultdict(
            lambda: [0.0, 0, [], 0, float("inf"), 0.0]
        )

        for record in records:
            route_stats[record.route][0] += record.duration
            route_stats[record.route][1] += 1
            route_stats[record.route][2].append(record.duration)
            route_stats[record.route][3] += 1 if record.status_code >= 400 else 0
            route_stats[record.route][4] = min(
                route_stats[record.route][4], record.duration
            )
            route_stats[record.route][5] = max(
                route_stats[record.route][5], record.duration
            )

        return sorted(
            [
                RouteStats(
                    route=route,
                    count=count,
                    avg=total / count if count else 0,
                    p95=_percentile(sorted(durations), 95),
                    p99=_percentile(sorted(durations), 99),
                    error_count=errors,
                    error_rate=(errors / count * 100) if count else 0,
                    min_duration=min_dur if min_dur != float("inf") else 0,
                    max_duration=max_dur,
                )
                for route, (
                    total,
                    count,
                    durations,
                    errors,
                    min_dur,
                    max_dur,
                ) in route_stats.items()
            ],
            key=lambda r: r.avg,
            reverse=True,
        )

    def _compute_route_tag_breakdown_from_records(
        self, records: list[PerformanceRecord]
    ) -> dict[str, dict[str, RouteTagStats]]:
        """Compute route-tag breakdown from a list of records."""
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

    def _get_cache_key(
        self, operation: str, query: PerformanceRecordQueryBuilder
    ) -> str:
        """Generate a cache key based on the query parameters."""
        key_parts = [
            operation,
            query.tag or "",
            query.route or "",
            query.since.isoformat() if query.since else "",
            query.until.isoformat() if query.until else "",
            query.order_by_field or "",
            query.order_direction or "",
            str(query.limit_records or ""),
            getattr(query, "route_filter", "") or "",
            getattr(query, "tag_filter", "") or "",
            str(getattr(query, "status_code_filter", "") or ""),
        ]
        key_string = "|".join(key_parts)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"{CACHE_PREFIX}{operation}:{key_hash}"

    def _get_cached_records(self, cache_key: str) -> list[PerformanceRecord] | None:
        """Retrieve cached records from Redis."""
        cached = self.redis.get(cache_key)
        if not cached:
            return None

        try:
            data = json.loads(cached)
            return PerformanceRecord.from_dict_list(data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to deserialize cached records: {e}")
            return None

    def _cache_result(self, cache_key: str, data: list | dict) -> None:
        try:
            self.redis.setex(cache_key, self.cache_ttl_seconds, json.dumps(data))
        except Exception as e:
            logger.warning(f"Failed to cache result: {e}")

    def _datetime_to_stream_id(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        timestamp_ms = int(dt.timestamp() * 1000)
        return f"{timestamp_ms}-0"

    def _parse_stream_entries(self, entries: list) -> list[PerformanceRecord]:
        records = []

        for _, data in entries:
            with suppress(KeyError, ValueError, json.JSONDecodeError):
                record = PerformanceRecord(
                    request_id=data["request_id"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    duration=float(data["duration"]),
                    route=data["route"],
                    status_code=int(data["status_code"]),
                    method=data["method"],
                    tags=json.loads(data["tags"]),
                )
                records.append(record)

        return records

    def is_recording_enabled(self) -> bool:
        """Check if recording is currently enabled."""
        # If key doesn't exist, default to enabled
        value = self.redis.get(RECORDING_ENABLED_KEY)
        if value is None:
            return True
        return value.lower() in ("true", "1", "yes")

    def enable_recording(self) -> None:
        """Enable recording of performance data."""
        self.redis.set(RECORDING_ENABLED_KEY, "true")

    def disable_recording(self) -> None:
        """Disable recording of performance data."""
        self.redis.set(RECORDING_ENABLED_KEY, "false")

    def clear_data(self) -> None:
        """Clear all performance data."""
        keys = self.redis.keys("perf:*")
        if not keys:
            return

        self.redis.delete(*keys)


def _percentile(sorted_durations: list[float], p: float) -> float:
    if not sorted_durations:
        return 0.0
    idx = max(0, math.ceil(p / 100 * len(sorted_durations)) - 1)
    return sorted_durations[idx]
