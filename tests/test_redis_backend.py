from datetime import datetime, timezone
from unittest.mock import patch

import fakeredis
import pytest

from views_perf_monitor.backends import (
    PerformanceRecordQueryBuilder,
)
from views_perf_monitor.backends.redis import (
    KEY_PREFIX,
    ROUTE_INDEX_KEY,
    ROUTE_KEY_PREFIX,
    TAG_INDEX_KEY,
    TAG_KEY_PREFIX,
    RedisBackend,
)
from views_perf_monitor.models import PerformanceRecord


def make_record(
    request_id: str = "req-1",
    route: str = "/api/users/",
    tags: list[str] | None = None,
    duration: float = 0.1,
    status_code: int = 200,
    method: str = "GET",
    timestamp: datetime | None = None,
) -> PerformanceRecord:
    return PerformanceRecord(
        request_id=request_id,
        timestamp=timestamp or datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        duration=duration,
        route=route,
        status_code=status_code,
        method=method,
        tags=tags if tags is not None else [],
    )


@pytest.fixture()
def fake_redis():
    return fakeredis.FakeRedis()


@pytest.fixture()
def backend(fake_redis):
    b = RedisBackend.__new__(RedisBackend)
    b.redis = fake_redis
    b.ttl = 30 * 86400
    return b


class TestSave:
    def test_saves_record_json_under_key(self, backend, fake_redis):
        record = make_record(request_id="abc123")
        backend.save(record)

        raw = fake_redis.get(f"{KEY_PREFIX}abc123")
        assert raw is not None
        parsed = PerformanceRecord.model_validate_json(raw)
        assert parsed.request_id == "abc123"

    def test_sets_ttl_on_record_key(self, backend, fake_redis):
        record = make_record(request_id="ttl-test")
        backend.save(record)

        ttl = fake_redis.ttl(f"{KEY_PREFIX}ttl-test")
        assert ttl > 0

    def test_adds_tags_to_tag_index(self, backend, fake_redis):
        record = make_record(tags=["api", "admin"])
        backend.save(record)

        members = {m.decode() for m in fake_redis.smembers(TAG_INDEX_KEY)}
        assert members == {"api", "admin"}

    def test_adds_request_id_to_tag_lists(self, backend, fake_redis):
        record = make_record(request_id="req-tag", tags=["api"])
        backend.save(record)

        ids = [v.decode() for v in fake_redis.lrange(f"{TAG_KEY_PREFIX}api", 0, -1)]
        assert "req-tag" in ids

    def test_sets_ttl_on_tag_list_key(self, backend, fake_redis):
        record = make_record(request_id="req-ttl", tags=["api"])
        backend.save(record)

        ttl = fake_redis.ttl(f"{TAG_KEY_PREFIX}api")
        assert ttl > 0

    def test_no_tag_index_entry_when_no_tags(self, backend, fake_redis):
        record = make_record(tags=[])
        backend.save(record)

        assert fake_redis.smembers(TAG_INDEX_KEY) == set()

    def test_adds_route_to_route_index(self, backend, fake_redis):
        record = make_record(route="/api/orders/")
        backend.save(record)

        members = {m.decode() for m in fake_redis.smembers(ROUTE_INDEX_KEY)}
        assert "/api/orders/" in members

    def test_adds_request_id_to_route_list(self, backend, fake_redis):
        record = make_record(request_id="req-route", route="/api/orders/")
        backend.save(record)

        ids = [
            v.decode()
            for v in fake_redis.lrange(f"{ROUTE_KEY_PREFIX}/api/orders/", 0, -1)
        ]
        assert "req-route" in ids

    def test_sets_ttl_on_route_list_key(self, backend, fake_redis):
        record = make_record(route="/api/items/")
        backend.save(record)

        ttl = fake_redis.ttl(f"{ROUTE_KEY_PREFIX}/api/items/")
        assert ttl > 0

    def test_multiple_records_accumulate_in_route_list(self, backend, fake_redis):
        backend.save(make_record(request_id="r1", route="/api/"))
        backend.save(make_record(request_id="r2", route="/api/"))

        ids = [v.decode() for v in fake_redis.lrange(f"{ROUTE_KEY_PREFIX}/api/", 0, -1)]
        assert set(ids) == {"r1", "r2"}


class TestGetAllTags:
    def test_returns_sorted_tags(self, backend):
        backend.save(make_record(request_id="r1", tags=["zebra", "alpha"]))
        backend.save(make_record(request_id="r2", tags=["beta"]))

        assert backend.get_all_tags() == ["alpha", "beta", "zebra"]

    def test_returns_empty_list_when_no_tags(self, backend):
        assert backend.get_all_tags() == []


class TestGetAllRoutes:
    def test_returns_sorted_routes(self, backend):
        backend.save(make_record(request_id="r1", route="/b/"))
        backend.save(make_record(request_id="r2", route="/a/"))

        assert backend.get_all_routes() == ["/a/", "/b/"]

    def test_returns_empty_list_when_no_routes(self, backend):
        assert backend.get_all_routes() == []


class TestFetchAll:
    def test_returns_all_saved_records(self, backend):
        backend.save(make_record(request_id="r1"))
        backend.save(make_record(request_id="r2"))

        records = backend.fetch(PerformanceRecordQueryBuilder.all())
        assert {r.request_id for r in records} == {"r1", "r2"}

    def test_returns_empty_when_nothing_saved(self, backend):
        records = backend.fetch(PerformanceRecordQueryBuilder.all())
        assert records == []

    def test_filters_by_since(self, backend):
        early = make_record(
            request_id="early",
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        late = make_record(
            request_id="late",
            timestamp=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
        )
        backend.save(early)
        backend.save(late)

        query = PerformanceRecordQueryBuilder.all().for_date_range(
            since=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc), until=None
        )
        records = backend.fetch(query)
        assert {r.request_id for r in records} == {"late"}

    def test_filters_by_until(self, backend):
        early = make_record(
            request_id="early",
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        late = make_record(
            request_id="late",
            timestamp=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
        )
        backend.save(early)
        backend.save(late)

        query = PerformanceRecordQueryBuilder.all().for_date_range(
            since=None,
            until=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        records = backend.fetch(query)
        assert {r.request_id for r in records} == {"early"}

    def test_order_by_duration(self, backend):
        backend.save(make_record(request_id="fast", duration=0.05))
        backend.save(make_record(request_id="slow", duration=0.5))
        backend.save(make_record(request_id="medium", duration=0.2))

        query = PerformanceRecordQueryBuilder.all().order_by("duration")
        records = backend.fetch(query)
        durations = [r.duration for r in records]
        assert durations == sorted(durations)


class TestFetchByTag:
    def test_returns_records_for_given_tag(self, backend):
        backend.save(make_record(request_id="r1", tags=["api"]))
        backend.save(make_record(request_id="r2", tags=["admin"]))

        records = backend.fetch(PerformanceRecordQueryBuilder.for_tag("api"))
        assert {r.request_id for r in records} == {"r1"}

    def test_returns_empty_for_unknown_tag(self, backend):
        records = backend.fetch(PerformanceRecordQueryBuilder.for_tag("nonexistent"))
        assert records == []

    def test_filter_by_route_within_tag(self, backend):
        backend.save(make_record(request_id="r1", tags=["api"], route="/api/users/"))
        backend.save(make_record(request_id="r2", tags=["api"], route="/api/orders/"))

        query = PerformanceRecordQueryBuilder.for_tag("api").filter_by_route(
            "/api/users/"
        )
        records = backend.fetch(query)
        assert {r.request_id for r in records} == {"r1"}


class TestFetchByRoute:
    def test_returns_records_for_given_route(self, backend):
        backend.save(make_record(request_id="r1", route="/api/users/"))
        backend.save(make_record(request_id="r2", route="/api/orders/"))

        records = backend.fetch(PerformanceRecordQueryBuilder.for_route("/api/users/"))
        assert {r.request_id for r in records} == {"r1"}

    def test_returns_empty_for_unknown_route(self, backend):
        records = backend.fetch(
            PerformanceRecordQueryBuilder.for_route("/nonexistent/")
        )
        assert records == []

    def test_filter_by_tag_within_route(self, backend):
        backend.save(
            make_record(request_id="r1", route="/api/users/", tags=["api", "v2"])
        )
        backend.save(
            make_record(request_id="r2", route="/api/users/", tags=["api", "v1"])
        )

        query = PerformanceRecordQueryBuilder.for_route("/api/users/").filter_by_tag(
            "v2"
        )
        records = backend.fetch(query)
        assert {r.request_id for r in records} == {"r1"}


class TestInit:
    def test_ttl_computed_from_days(self):
        with patch("views_perf_monitor.backends.redis.Redis") as MockRedis:
            MockRedis.from_url.return_value = fakeredis.FakeRedis()
            b = RedisBackend(redis_url="redis://localhost", ttl_days=7)

        assert b.ttl == 7 * 86400

    def test_default_ttl(self):
        with patch("views_perf_monitor.backends.redis.Redis") as MockRedis:
            MockRedis.from_url.return_value = fakeredis.FakeRedis()
            b = RedisBackend(redis_url="redis://localhost")

        assert b.ttl == 30 * 86400
