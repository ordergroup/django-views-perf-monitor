from redis import Redis

from views_perf_monitor.backends import (
    PerformanceMonitorBackend,
    PerformanceRecordQueryBuilder,
)
from views_perf_monitor.models import PerformanceRecord

KEY_PREFIX = "perf:route:"  # set of all requests
TAG_KEY_PREFIX = "perf:tag:"  # set of request ids per tag
TAG_INDEX_KEY = "perf:tags"  # a Set of all known tags
ROUTE_KEY_PREFIX = "perf:route_idx:"  # list of request ids per route
ROUTE_INDEX_KEY = "perf:routes"  # a Set of all known routes

DEFAULT_TTL_DAYS = 30


class RedisBackend(PerformanceMonitorBackend):
    def __init__(self, redis_url: str, ttl_days: int = DEFAULT_TTL_DAYS):
        self.redis = Redis.from_url(redis_url)
        self.ttl = ttl_days * 86400

    def save(self, record: PerformanceRecord):
        payload = record.model_dump_json()
        key = f"{KEY_PREFIX}{record.request_id}"
        with self.redis.pipeline() as pipe:
            pipe.set(key, payload, ex=self.ttl)
            if record.tags:
                pipe.sadd(TAG_INDEX_KEY, *record.tags)
            for tag in record.tags:
                tag_key = f"{TAG_KEY_PREFIX}{tag}"
                pipe.lpush(tag_key, str(record.request_id))
                pipe.expire(tag_key, self.ttl)
            route_key = f"{ROUTE_KEY_PREFIX}{record.route}"
            pipe.sadd(ROUTE_INDEX_KEY, record.route)
            pipe.lpush(route_key, str(record.request_id))
            pipe.expire(route_key, self.ttl)
            pipe.execute()

    def get_all_tags(self) -> list[str]:
        return sorted(t.decode() for t in self.redis.smembers(TAG_INDEX_KEY))

    def get_all_routes(self) -> list[str]:
        return sorted(r.decode() for r in self.redis.smembers(ROUTE_INDEX_KEY))

    def fetch(self, query: PerformanceRecordQueryBuilder) -> list[PerformanceRecord]:
        if query.tag:
            records = self._fetch_by_tag(query.tag)
        elif query.route:
            records = self._fetch_by_route(query.route)
        else:
            records = self._fetch_all()

        # filtering and sorting will not be done in redis
        if query.since:
            records = [r for r in records if r.timestamp >= query.since]
        if query.until:
            records = [r for r in records if r.timestamp <= query.until]

        if route_filter := getattr(query, "route_filter", None):
            records = [r for r in records if r.route == route_filter]

        if tag_filter := getattr(query, "tag_filter", None):
            records = [r for r in records if tag_filter in r.tags]

        if query.order_by_field:
            records = sorted(records, key=lambda r: getattr(r, query.order_by_field))

        return records

    def _fetch_all(self) -> list[PerformanceRecord]:
        keys = list(self.redis.scan_iter(f"{KEY_PREFIX}*"))
        if not keys:
            return []

        with self.redis.pipeline() as pipe:
            for key in keys:
                pipe.get(key)
            raw_records = pipe.execute()

        return PerformanceRecord.from_raw_records(raw_records)

    def _fetch_by_tag(self, tag: str) -> list[PerformanceRecord]:
        request_ids = self.redis.lrange(f"{TAG_KEY_PREFIX}{tag}", 0, -1)
        if not request_ids:
            return []

        with self.redis.pipeline() as pipe:
            for rid in request_ids:
                pipe.get(f"{KEY_PREFIX}{rid.decode()}")
            raw_records = pipe.execute()

        return PerformanceRecord.from_raw_records(raw_records)

    def _fetch_by_route(self, route: str) -> list[PerformanceRecord]:
        request_ids = self.redis.lrange(f"{ROUTE_KEY_PREFIX}{route}", 0, -1)
        if not request_ids:
            return []

        with self.redis.pipeline() as pipe:
            for rid in request_ids:
                pipe.get(f"{KEY_PREFIX}{rid.decode()}")
            raw_records = pipe.execute()

        return PerformanceRecord.from_raw_records(raw_records)
