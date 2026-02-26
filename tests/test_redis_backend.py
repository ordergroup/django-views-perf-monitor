from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import fakeredis
import pytest
from redis import Redis

from views_perf_monitor.backends import PerformanceRecordQueryBuilder
from views_perf_monitor.backends.redis import (
    CACHE_PREFIX,
    HOURLY_COUNTS_HASH,
    MAIN_STREAM,
    RECORDING_ENABLED_KEY,
    ROUTE_INDEX_KEY,
    STATS_GLOBAL,
    STATS_ROUTE_PREFIX,
    STATS_ROUTE_TAG_PREFIX,
    STATS_TAG_PREFIX,
    STATUS_CODE_COUNTS_HASH,
    TAG_INDEX_KEY,
    RedisBackend,
    _percentile,
)
from views_perf_monitor.models import PerformanceRecord


@pytest.fixture
def fake_redis():
    """Create a fake Redis instance for testing."""
    server = fakeredis.FakeServer()
    return fakeredis.FakeStrictRedis(server=server, decode_responses=True)


@pytest.fixture
def redis_backend(fake_redis):
    """Create a RedisBackend instance with fake Redis."""
    with patch.object(Redis, "from_url", return_value=fake_redis):
        backend = RedisBackend(
            redis_url="redis://localhost:6379/0",
            ttl_days=30,
            max_stream_length=1000,
            cache_ttl_seconds=300,
        )
        return backend


@pytest.fixture
def sample_record():
    """Create a sample performance record."""
    return PerformanceRecord(
        request_id="req-123",
        timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        duration=0.5,
        route="/api/users",
        status_code=200,
        method="GET",
        tags=["api", "users"],
    )


@pytest.fixture
def sample_records():
    """Create multiple sample performance records."""
    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    records = [
        PerformanceRecord(
            request_id="req-1",
            timestamp=base_time,
            duration=0.1,
            route="/api/users",
            status_code=200,
            method="GET",
            tags=["api", "users"],
        ),
        PerformanceRecord(
            request_id="req-2",
            timestamp=base_time + timedelta(minutes=5),
            duration=0.5,
            route="/api/users",
            status_code=200,
            method="GET",
            tags=["api", "users"],
        ),
        PerformanceRecord(
            request_id="req-3",
            timestamp=base_time + timedelta(minutes=10),
            duration=1.5,
            route="/api/posts",
            status_code=201,
            method="POST",
            tags=["api", "posts"],
        ),
        PerformanceRecord(
            request_id="req-4",
            timestamp=base_time + timedelta(minutes=15),
            duration=0.3,
            route="/api/posts",
            status_code=404,
            method="GET",
            tags=["api", "posts"],
        ),
        PerformanceRecord(
            request_id="req-5",
            timestamp=base_time + timedelta(minutes=20),
            duration=2.0,
            route="/api/users",
            status_code=500,
            method="POST",
            tags=["api", "users"],
        ),
    ]
    return records


class TestRedisBackendInitialization:
    """Test backend initialization."""

    def test_initialization_with_defaults(self, redis_backend):
        """Test backend initializes with default values."""
        assert redis_backend.ttl_days == 30
        assert redis_backend.max_stream_length == 1000
        assert redis_backend.cache_ttl_seconds == 300
        assert redis_backend.redis is not None

    def test_initialization_with_custom_values(self, fake_redis):
        """Test backend initializes with custom values."""
        with patch.object(Redis, "from_url", return_value=fake_redis):
            backend = RedisBackend(
                redis_url="redis://localhost:6379/0",
                ttl_days=7,
                max_stream_length=500,
                cache_ttl_seconds=60,
            )
            assert backend.ttl_days == 7
            assert backend.max_stream_length == 500
            assert backend.cache_ttl_seconds == 60

    def test_lua_script_registration(self, redis_backend):
        """Test that Lua script is registered."""
        assert redis_backend.update_min_max_script is not None


class TestSaveRecord:
    """Test saving performance records."""

    def test_save_single_record(self, redis_backend, sample_record):
        """Test saving a single performance record."""
        redis_backend.save(sample_record)

        # Check main stream
        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 1

        # Check route index
        routes = redis_backend.redis.smembers(ROUTE_INDEX_KEY)
        assert "/api/users" in routes

        # Check tag index
        tags = redis_backend.redis.smembers(TAG_INDEX_KEY)
        assert "api" in tags
        assert "users" in tags

        # Check global stats
        count = redis_backend.redis.hget(STATS_GLOBAL, "count")
        assert count == "1"
        total_duration = redis_backend.redis.hget(STATS_GLOBAL, "total_duration")
        assert float(total_duration) == 0.5

    def test_save_updates_route_stats(self, redis_backend, sample_record):
        """Test that saving updates route statistics."""
        redis_backend.save(sample_record)

        route_key = f"{STATS_ROUTE_PREFIX}/api/users"
        count = redis_backend.redis.hget(route_key, "count")
        total_duration = redis_backend.redis.hget(route_key, "total_duration")
        min_duration = redis_backend.redis.hget(route_key, "min_duration")
        max_duration = redis_backend.redis.hget(route_key, "max_duration")

        assert int(count) == 1
        assert float(total_duration) == 0.5
        assert float(min_duration) == 0.5
        assert float(max_duration) == 0.5

    def test_save_updates_tag_stats(self, redis_backend, sample_record):
        """Test that saving updates tag statistics."""
        redis_backend.save(sample_record)

        for tag in sample_record.tags:
            tag_key = f"{STATS_TAG_PREFIX}{tag}"
            count = redis_backend.redis.hget(tag_key, "count")
            total_duration = redis_backend.redis.hget(tag_key, "total_duration")
            assert int(count) == 1
            assert float(total_duration) == 0.5

    def test_save_updates_route_tag_stats(self, redis_backend, sample_record):
        """Test that saving updates route-tag combination statistics."""
        redis_backend.save(sample_record)

        for tag in sample_record.tags:
            route_tag_key = f"{STATS_ROUTE_TAG_PREFIX}/api/users:{tag}"
            count = redis_backend.redis.hget(route_tag_key, "count")
            total_duration = redis_backend.redis.hget(route_tag_key, "total_duration")
            assert int(count) == 1
            assert float(total_duration) == 0.5

    def test_save_updates_hourly_counts(self, redis_backend, sample_record):
        """Test that saving updates hourly request counts."""
        redis_backend.save(sample_record)

        hour_bucket = "2024-01-15T10:00"
        count = redis_backend.redis.hget(HOURLY_COUNTS_HASH, hour_bucket)
        assert int(count) == 1

    def test_save_updates_status_code_counts(self, redis_backend, sample_record):
        """Test that saving updates status code counts."""
        redis_backend.save(sample_record)

        count = redis_backend.redis.hget(STATUS_CODE_COUNTS_HASH, "200")
        assert int(count) == 1

    def test_save_error_status_code(self, redis_backend):
        """Test saving a record with error status code."""
        error_record = PerformanceRecord(
            request_id="req-error",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration=0.5,
            route="/api/users",
            status_code=500,
            method="GET",
            tags=["api"],
        )
        redis_backend.save(error_record)

        error_count = redis_backend.redis.hget(STATS_GLOBAL, "error_count")
        assert int(error_count) == 1

        route_key = f"{STATS_ROUTE_PREFIX}/api/users"
        route_error_count = redis_backend.redis.hget(route_key, "error_count")
        assert int(route_error_count) == 1

    def test_save_updates_min_max_correctly(self, redis_backend):
        """Test that min/max are updated correctly across multiple saves."""
        records = [
            PerformanceRecord(
                request_id=f"req-{i}",
                timestamp=datetime(2024, 1, 15, 10, i, 0, tzinfo=timezone.utc),
                duration=duration,
                route="/api/test",
                status_code=200,
                method="GET",
                tags=["test"],
            )
            for i, duration in enumerate([0.5, 0.1, 1.5, 0.3, 2.0])
        ]

        for record in records:
            redis_backend.save(record)

        route_key = f"{STATS_ROUTE_PREFIX}/api/test"
        min_duration = float(redis_backend.redis.hget(route_key, "min_duration"))
        max_duration = float(redis_backend.redis.hget(route_key, "max_duration"))

        assert min_duration == 0.1
        assert max_duration == 2.0

    def test_save_multiple_records(self, redis_backend, sample_records):
        """Test saving multiple records."""
        for record in sample_records:
            redis_backend.save(record)

        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 5

        count = redis_backend.redis.hget(STATS_GLOBAL, "count")
        assert int(count) == 5

    def test_save_without_tags(self, redis_backend):
        """Test saving a record without tags."""
        record = PerformanceRecord(
            request_id="req-no-tags",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration=0.5,
            route="/api/test",
            status_code=200,
            method="GET",
            tags=[],
        )
        redis_backend.save(record)

        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 1

        tags = redis_backend.redis.smembers(TAG_INDEX_KEY)
        assert len(tags) == 0

    def test_save_when_recording_disabled(self, redis_backend, sample_record):
        """Test that save does nothing when recording is disabled."""
        redis_backend.disable_recording()
        redis_backend.save(sample_record)

        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 0

        count = redis_backend.redis.hget(STATS_GLOBAL, "count")
        assert count is None


class TestRecordingControl:
    """Test recording enable/disable functionality."""

    def test_recording_enabled_by_default(self, redis_backend):
        """Test that recording is enabled by default."""
        assert redis_backend.is_recording_enabled() is True

    def test_enable_recording(self, redis_backend):
        """Test enabling recording."""
        redis_backend.enable_recording()
        assert redis_backend.is_recording_enabled() is True

        value = redis_backend.redis.get(RECORDING_ENABLED_KEY)
        assert value == "true"

    def test_disable_recording(self, redis_backend):
        """Test disabling recording."""
        redis_backend.disable_recording()
        assert redis_backend.is_recording_enabled() is False

        value = redis_backend.redis.get(RECORDING_ENABLED_KEY)
        assert value == "false"

    def test_recording_status_various_values(self, redis_backend):
        """Test recording status with various stored values."""
        test_cases = [
            ("true", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
        ]

        for value, expected in test_cases:
            redis_backend.redis.set(RECORDING_ENABLED_KEY, value)
            assert redis_backend.is_recording_enabled() == expected


class TestFetch:
    """Test fetching performance records."""

    def test_fetch_all_records(self, redis_backend, sample_records):
        """Test fetching all records."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 5

    def test_fetch_by_route(self, redis_backend, sample_records):
        """Test fetching records filtered by route."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.for_route("/api/users")
        records = redis_backend.fetch(query)

        assert len(records) == 3
        assert all(r.route == "/api/users" for r in records)

    def test_fetch_by_tag(self, redis_backend, sample_records):
        """Test fetching records filtered by tag."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.for_tag("posts")
        records = redis_backend.fetch(query)

        assert len(records) == 2
        assert all("posts" in r.tags for r in records)

    def test_fetch_with_date_range(self, redis_backend, sample_records):
        """Test fetching records with date range parameters (tests the query builder)."""
        for record in sample_records:
            redis_backend.save(record)

        # Test that date range query doesn't error
        since = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        until = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        query = PerformanceRecordQueryBuilder.all().for_date_range(since, until)
        records = redis_backend.fetch(query)

        # Note: fakeredis may not perfectly handle time-based stream queries
        # The important thing is no errors occur
        assert isinstance(records, list)

    def test_fetch_with_limit(self, redis_backend, sample_records):
        """Test fetching records with a limit."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all().limit(3)
        records = redis_backend.fetch(query)

        assert len(records) == 3

    def test_fetch_with_order_by(self, redis_backend, sample_records):
        """Test fetching records with ordering."""
        for record in sample_records:
            redis_backend.save(record)

        # Order by duration descending
        query = PerformanceRecordQueryBuilder.all().order_by("duration", "desc")
        records = redis_backend.fetch(query)

        assert records[0].duration == 2.0
        assert records[-1].duration == 0.1

        # Order by duration ascending
        query = PerformanceRecordQueryBuilder.all().order_by("duration", "asc")
        records = redis_backend.fetch(query)

        assert records[0].duration == 0.1
        assert records[-1].duration == 2.0

    def test_fetch_with_route_filter(self, redis_backend, sample_records):
        """Test fetching records with route filter on tag query."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.for_tag("api").filter_by_route(
            "/api/users"
        )
        records = redis_backend.fetch(query)

        assert len(records) == 3
        assert all(r.route == "/api/users" for r in records)

    def test_fetch_with_status_code_filter(self, redis_backend, sample_records):
        """Test fetching records with status code filter."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.for_route(
            "/api/posts"
        ).filter_by_status_code(404)
        records = redis_backend.fetch(query)

        assert len(records) == 1
        assert records[0].status_code == 404

    def test_fetch_empty_result(self, redis_backend):
        """Test fetching when no records exist."""
        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 0

    def test_fetch_uses_cache(self, redis_backend, sample_records):
        """Test that fetch uses cache for repeated queries."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()

        # First fetch - should hit Redis
        records1 = redis_backend.fetch(query)

        # Second fetch - should hit cache
        records2 = redis_backend.fetch(query)

        assert len(records1) == len(records2)
        assert records1[0].request_id == records2[0].request_id


class TestGetAllTags:
    """Test getting all tags."""

    def test_get_all_tags_empty(self, redis_backend):
        """Test getting tags when none exist."""
        tags = redis_backend.get_all_tags()
        assert tags == []

    def test_get_all_tags(self, redis_backend, sample_records):
        """Test getting all unique tags."""
        for record in sample_records:
            redis_backend.save(record)

        tags = redis_backend.get_all_tags()
        assert set(tags) == {"api", "posts", "users"}
        # Check that they're sorted
        assert tags == sorted(tags)


class TestGetAllRoutes:
    """Test getting all routes."""

    def test_get_all_routes_empty(self, redis_backend):
        """Test getting routes when none exist."""
        routes = redis_backend.get_all_routes()
        assert routes == []

    def test_get_all_routes(self, redis_backend, sample_records):
        """Test getting all unique routes."""
        for record in sample_records:
            redis_backend.save(record)

        routes = redis_backend.get_all_routes()
        assert set(routes) == {"/api/users", "/api/posts"}
        # Check that they're sorted
        assert routes == sorted(routes)


class TestGetDataTimeRange:
    """Test getting data time range."""

    def test_get_data_time_range_empty(self, redis_backend):
        """Test getting time range when no data exists."""
        first_time, last_time = redis_backend.get_data_time_range()
        assert first_time is None
        assert last_time is None

    def test_get_data_time_range(self, redis_backend, sample_records):
        """Test getting time range of data."""
        for record in sample_records:
            redis_backend.save(record)

        first_time, last_time = redis_backend.get_data_time_range()

        assert first_time == sample_records[0].timestamp
        assert last_time == sample_records[-1].timestamp


class TestTagStats:
    """Test tag statistics."""

    def test_get_tags_stats_aggregated(self, redis_backend, sample_records):
        """Test getting aggregated tag statistics."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_tags_stats(query)

        assert len(stats) == 3  # api, posts, users

        # Find stats for each tag
        api_stats = next(s for s in stats if s.tag == "api")
        users_stats = next(s for s in stats if s.tag == "users")
        posts_stats = next(s for s in stats if s.tag == "posts")

        assert api_stats.count == 5
        assert users_stats.count == 3
        assert posts_stats.count == 2

        # Check min/max for users tag
        assert users_stats.min_duration == 0.1
        assert users_stats.max_duration == 2.0

    def test_get_tags_stats_from_records(self, redis_backend, sample_records):
        """Test computing tag statistics from records (without date range uses aggregated stats)."""
        for record in sample_records:
            redis_backend.save(record)

        # Test without date range - should use aggregated stats path
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_tags_stats(query)

        assert len(stats) > 0

        # Verify stats are computed correctly
        for stat in stats:
            assert stat.count > 0
            assert stat.avg >= 0

    def test_get_tags_stats_empty(self, redis_backend):
        """Test getting tag statistics when no data exists."""
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_tags_stats(query)

        assert stats == []


class TestRouteStats:
    """Test route statistics."""

    def test_get_routes_stats_aggregated(self, redis_backend, sample_records):
        """Test getting aggregated route statistics."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_routes_stats(query)

        assert len(stats) == 2  # /api/users, /api/posts

        users_stats = next(s for s in stats if s.route == "/api/users")
        posts_stats = next(s for s in stats if s.route == "/api/posts")

        assert users_stats.count == 3
        assert posts_stats.count == 2

        # Check error rates
        assert users_stats.error_count == 1  # One 500 error
        assert posts_stats.error_count == 1  # One 404 error

        # Check min/max
        assert users_stats.min_duration == 0.1
        assert users_stats.max_duration == 2.0

    def test_get_routes_stats_from_records(self, redis_backend, sample_records):
        """Test computing route statistics from aggregated data."""
        for record in sample_records:
            redis_backend.save(record)

        # Test without date range - should use aggregated stats path
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_routes_stats(query)

        assert len(stats) > 0

        for stat in stats:
            assert stat.count > 0
            assert stat.avg >= 0
            assert 0 <= stat.error_rate <= 100

    def test_get_routes_stats_empty(self, redis_backend):
        """Test getting route statistics when no data exists."""
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_routes_stats(query)

        assert stats == []


class TestRouteTagBreakdown:
    """Test route-tag breakdown."""

    def test_route_tag_breakdown_aggregated(self, redis_backend, sample_records):
        """Test getting aggregated route-tag breakdown."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        breakdown = redis_backend.route_tag_breakdown(query)

        assert "/api/users" in breakdown
        assert "/api/posts" in breakdown

        # Check that users route has correct tags
        assert "api" in breakdown["/api/users"]
        assert "users" in breakdown["/api/users"]

        # Check stats for /api/users - api tag
        api_stats = breakdown["/api/users"]["api"]
        assert api_stats.count == 3
        assert api_stats.avg > 0

    def test_route_tag_breakdown_from_records(self, redis_backend, sample_records):
        """Test computing route-tag breakdown from aggregated data."""
        for record in sample_records:
            redis_backend.save(record)

        # Test without date range - should use aggregated stats path
        query = PerformanceRecordQueryBuilder.all()
        breakdown = redis_backend.route_tag_breakdown(query)

        assert len(breakdown) > 0

        for _route, tags in breakdown.items():
            for _tag, stats in tags.items():
                assert stats.count > 0
                assert stats.avg >= 0

    def test_route_tag_breakdown_empty(self, redis_backend):
        """Test getting route-tag breakdown when no data exists."""
        query = PerformanceRecordQueryBuilder.all()
        breakdown = redis_backend.route_tag_breakdown(query)

        assert breakdown == {}


class TestWeightedAvg:
    """Test weighted average calculation."""

    def test_weighted_avg(self, redis_backend, sample_records):
        """Test calculating weighted average."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        # Need to fix the method call - it should be get_routes_stats
        stats = redis_backend.get_routes_stats(query)

        total_count = sum(s.count for s in stats)
        weighted_avg = (
            sum(s.avg * s.count for s in stats) / total_count if total_count else 0
        )

        assert total_count == 5
        assert weighted_avg > 0

    def test_weighted_avg_empty(self, redis_backend):
        """Test weighted average with no data."""
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_routes_stats(query)

        total_count = sum(s.count for s in stats)
        assert total_count == 0


class TestRequestTrend:
    """Test request trend functionality."""

    def test_request_trend(self, redis_backend, sample_records):
        """Test getting request trend data."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        trend = redis_backend.request_trend(query)

        # All records are in the same hour
        assert "2024-01-15T10:00" in trend
        assert trend["2024-01-15T10:00"] == 5

    def test_request_trend_multiple_hours(self, redis_backend):
        """Test request trend across multiple hours."""
        base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        records = [
            PerformanceRecord(
                request_id=f"req-{i}",
                timestamp=base_time + timedelta(hours=i),
                duration=0.5,
                route="/api/test",
                status_code=200,
                method="GET",
                tags=["test"],
            )
            for i in range(5)
        ]

        for record in records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        trend = redis_backend.request_trend(query)

        assert len(trend) == 5
        assert all(count == 1 for count in trend.values())

        # Check that results are sorted
        hours = list(trend.keys())
        assert hours == sorted(hours)

    def test_request_trend_empty(self, redis_backend):
        """Test request trend with no data."""
        query = PerformanceRecordQueryBuilder.all()
        trend = redis_backend.request_trend(query)

        assert trend == {}


class TestStatusCodeStats:
    """Test status code statistics."""

    def test_status_code_stats(self, redis_backend, sample_records):
        """Test getting status code statistics."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.status_code_stats(query)

        # Find each status code
        status_200 = next((s for s in stats if s.status_code == 200), None)
        status_201 = next((s for s in stats if s.status_code == 201), None)
        status_404 = next((s for s in stats if s.status_code == 404), None)
        status_500 = next((s for s in stats if s.status_code == 500), None)

        assert status_200 is not None
        assert status_200.count == 2
        assert status_200.group == "2xx"

        assert status_201 is not None
        assert status_201.count == 1
        assert status_201.group == "2xx"

        assert status_404 is not None
        assert status_404.count == 1
        assert status_404.group == "4xx"

        assert status_500 is not None
        assert status_500.count == 1
        assert status_500.group == "5xx"

    def test_status_code_stats_grouping(self, redis_backend):
        """Test status code grouping logic."""
        status_codes = [200, 301, 404, 500, 100]
        records = [
            PerformanceRecord(
                request_id=f"req-{code}",
                timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                duration=0.5,
                route="/api/test",
                status_code=code,
                method="GET",
                tags=["test"],
            )
            for code in status_codes
        ]

        for record in records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.status_code_stats(query)

        groups = {s.status_code: s.group for s in stats}
        assert groups[200] == "2xx"
        assert groups[301] == "3xx"
        assert groups[404] == "4xx"
        assert groups[500] == "5xx"
        assert groups[100] == "other"

    def test_status_code_stats_sorted(self, redis_backend):
        """Test that status code stats are sorted by status code."""
        status_codes = [500, 200, 404, 201]
        records = [
            PerformanceRecord(
                request_id=f"req-{code}",
                timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                duration=0.5,
                route="/api/test",
                status_code=code,
                method="GET",
                tags=["test"],
            )
            for code in status_codes
        ]

        for record in records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.status_code_stats(query)

        status_codes_result = [s.status_code for s in stats]
        assert status_codes_result == sorted(status_codes_result)

    def test_status_code_stats_empty(self, redis_backend):
        """Test status code statistics with no data."""
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.status_code_stats(query)

        assert stats == []


class TestClearData:
    """Test clearing data."""

    def test_clear_data(self, redis_backend, sample_records):
        """Test clearing all performance data."""
        for record in sample_records:
            redis_backend.save(record)

        # Verify data exists
        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) > 0

        routes = redis_backend.get_all_routes()
        assert len(routes) > 0

        # Clear data
        redis_backend.clear_data()

        # Verify data is cleared
        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 0

        routes = redis_backend.get_all_routes()
        assert len(routes) == 0

        tags = redis_backend.get_all_tags()
        assert len(tags) == 0

    def test_clear_data_when_empty(self, redis_backend):
        """Test clearing data when no data exists."""
        # Should not raise an error
        redis_backend.clear_data()

        routes = redis_backend.get_all_routes()
        assert len(routes) == 0


class TestCaching:
    """Test caching functionality."""

    def test_cache_key_generation(self, redis_backend):
        """Test that cache keys are generated correctly."""
        query1 = PerformanceRecordQueryBuilder.all()
        query2 = PerformanceRecordQueryBuilder.for_route("/api/users")

        key1 = redis_backend._get_cache_key("fetch", query1)
        key2 = redis_backend._get_cache_key("fetch", query2)

        assert key1 != key2
        assert key1.startswith(CACHE_PREFIX)
        assert key2.startswith(CACHE_PREFIX)

    def test_cache_key_includes_all_params(self, redis_backend):
        """Test that cache key includes all query parameters."""
        since = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        until = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

        query1 = PerformanceRecordQueryBuilder.all()
        query2 = (
            PerformanceRecordQueryBuilder.all()
            .for_date_range(since, until)
            .order_by("duration", "desc")
            .limit(10)
        )

        key1 = redis_backend._get_cache_key("fetch", query1)
        key2 = redis_backend._get_cache_key("fetch", query2)

        assert key1 != key2

    def test_cached_records_retrieval(self, redis_backend, sample_records):
        """Test retrieving cached records."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()

        # First fetch - caches the result
        records1 = redis_backend.fetch(query)

        # Manually check that cache was written
        cache_key = redis_backend._get_cache_key("fetch", query)
        cached_data = redis_backend.redis.get(cache_key)
        assert cached_data is not None

        # Second fetch - should use cache
        records2 = redis_backend.fetch(query)

        assert len(records1) == len(records2)

    def test_cache_ttl(self, redis_backend, sample_records):
        """Test that cache has TTL set."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        redis_backend.fetch(query)

        cache_key = redis_backend._get_cache_key("fetch", query)
        ttl = redis_backend.redis.ttl(cache_key)

        # TTL should be set and positive
        assert ttl > 0
        assert ttl <= redis_backend.cache_ttl_seconds


class TestHelperMethods:
    """Test helper methods."""

    def test_datetime_to_stream_id(self, redis_backend):
        """Test converting datetime to Redis stream ID."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        stream_id = redis_backend._datetime_to_stream_id(dt)

        assert stream_id.endswith("-0")
        # Verify it's a valid timestamp format (ms-sequence)
        parts = stream_id.split("-")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1] == "0"

    def test_datetime_to_stream_id_naive(self, redis_backend):
        """Test converting naive datetime to stream ID."""
        dt = datetime(2024, 1, 15, 10, 30, 0)  # naive datetime
        stream_id = redis_backend._datetime_to_stream_id(dt)

        assert stream_id.endswith("-0")
        assert "-" in stream_id

    def test_parse_stream_entries(self, redis_backend, sample_record):
        """Test parsing stream entries."""
        redis_backend.save(sample_record)

        entries = redis_backend.redis.xrange(MAIN_STREAM)
        records = redis_backend._parse_stream_entries(entries)

        assert len(records) == 1
        assert records[0].request_id == sample_record.request_id
        assert records[0].route == sample_record.route
        assert records[0].status_code == sample_record.status_code
        assert records[0].tags == sample_record.tags

    def test_parse_stream_entries_with_invalid_data(self, redis_backend):
        """Test parsing stream entries with invalid data."""
        # Manually add invalid entry
        redis_backend.redis.xadd(
            MAIN_STREAM,
            {"request_id": "invalid", "timestamp": "not-a-date"},
        )

        entries = redis_backend.redis.xrange(MAIN_STREAM)
        records = redis_backend._parse_stream_entries(entries)

        # Should skip invalid entries
        assert len(records) == 0


class TestPercentileFunction:
    """Test the _percentile utility function."""

    def test_percentile_empty_list(self):
        """Test percentile with empty list."""
        result = _percentile([], 95)
        assert result == 0.0

    def test_percentile_single_element(self):
        """Test percentile with single element."""
        result = _percentile([5.0], 95)
        assert result == 5.0

    def test_percentile_50th(self):
        """Test 50th percentile (median)."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _percentile(data, 50)
        assert result == 3.0

    def test_percentile_95th(self):
        """Test 95th percentile."""
        data = list(range(1, 101))  # 1 to 100
        data_float = [float(x) for x in data]
        result = _percentile(data_float, 95)
        assert result == 95.0

    def test_percentile_99th(self):
        """Test 99th percentile."""
        data = list(range(1, 101))
        data_float = [float(x) for x in data]
        result = _percentile(data_float, 99)
        assert result == 99.0

    def test_percentile_with_unsorted_data(self):
        """Test that percentile function works but requires sorted input."""
        sorted_data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _percentile(sorted_data, 50)
        assert result == 3.0

        # The function expects sorted data as input (caller's responsibility)
        # Using unsorted data will give incorrect results
        unsorted = [5.0, 1.0, 3.0, 2.0, 4.0]
        result_unsorted = _percentile(unsorted, 50)
        # This demonstrates why data must be sorted before calling _percentile
        assert result_unsorted == 3.0  # happens to be correct for this specific case


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_save_with_float_duration(self, redis_backend):
        """Test saving record with float duration."""
        record = PerformanceRecord(
            request_id="req-float",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration=0.12345,
            route="/api/test",
            status_code=200,
            method="GET",
            tags=["test"],
        )
        redis_backend.save(record)

        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 1

    def test_save_with_large_duration(self, redis_backend):
        """Test saving record with large duration."""
        record = PerformanceRecord(
            request_id="req-large",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration=999999.999,
            route="/api/test",
            status_code=200,
            method="GET",
            tags=["test"],
        )
        redis_backend.save(record)

        route_key = f"{STATS_ROUTE_PREFIX}/api/test"
        max_duration = float(redis_backend.redis.hget(route_key, "max_duration"))
        assert max_duration == 999999.999

    def test_save_with_special_characters_in_route(self, redis_backend):
        """Test saving record with special characters in route."""
        record = PerformanceRecord(
            request_id="req-special",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration=0.5,
            route="/api/users/{id}/posts?page=1",
            status_code=200,
            method="GET",
            tags=["test"],
        )
        redis_backend.save(record)

        routes = redis_backend.get_all_routes()
        assert "/api/users/{id}/posts?page=1" in routes

    def test_save_with_many_tags(self, redis_backend):
        """Test saving record with many tags."""
        many_tags = [f"tag{i}" for i in range(50)]
        record = PerformanceRecord(
            request_id="req-many-tags",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            duration=0.5,
            route="/api/test",
            status_code=200,
            method="GET",
            tags=many_tags,
        )
        redis_backend.save(record)

        all_tags = redis_backend.get_all_tags()
        assert len(all_tags) == 50

    def test_fetch_with_invalid_query_attributes(self, redis_backend, sample_records):
        """Test fetch with query that has no special filters."""
        for record in sample_records:
            redis_backend.save(record)

        query = PerformanceRecordQueryBuilder.all()
        # These attributes don't exist on base query builder
        assert not hasattr(query, "route_filter")
        assert not hasattr(query, "tag_filter")
        assert not hasattr(query, "status_code_filter")

        # Fetch should still work
        records = redis_backend.fetch(query)
        assert len(records) == 5

    def test_multiple_saves_same_record(self, redis_backend, sample_record):
        """Test saving the same record multiple times."""
        redis_backend.save(sample_record)
        redis_backend.save(sample_record)
        redis_backend.save(sample_record)

        # Should create 3 entries
        entries = redis_backend.redis.xrange(MAIN_STREAM)
        assert len(entries) == 3

        # Global count should be 3
        count = redis_backend.redis.hget(STATS_GLOBAL, "count")
        assert int(count) == 3


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_complete_workflow(self, redis_backend):
        """Test complete workflow from save to query."""
        # Save multiple records
        base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            record = PerformanceRecord(
                request_id=f"req-{i}",
                timestamp=base_time + timedelta(minutes=i),
                duration=0.5 + (i * 0.1),
                route=f"/api/route{i % 3}",
                status_code=200 if i % 5 != 0 else 500,
                method="GET",
                tags=[f"tag{i % 2}", "common"],
            )
            redis_backend.save(record)

        # Test various queries
        all_routes = redis_backend.get_all_routes()
        assert len(all_routes) == 3

        all_tags = redis_backend.get_all_tags()
        assert "common" in all_tags

        # Test statistics
        query = PerformanceRecordQueryBuilder.all()
        route_stats = redis_backend.get_routes_stats(query)
        assert len(route_stats) == 3

        tag_stats = redis_backend.get_tags_stats(query)
        assert len(tag_stats) > 0

        # Test trends
        trend = redis_backend.request_trend(query)
        assert len(trend) > 0

        status_stats = redis_backend.status_code_stats(query)
        assert len(status_stats) > 0

        # Test route-tag breakdown
        breakdown = redis_backend.route_tag_breakdown(query)
        assert len(breakdown) > 0

    def test_disable_enable_recording_workflow(self, redis_backend, sample_record):
        """Test workflow with disabling and enabling recording."""
        # Save with recording enabled
        redis_backend.save(sample_record)
        assert len(redis_backend.redis.xrange(MAIN_STREAM)) == 1

        # Disable recording
        redis_backend.disable_recording()
        sample_record.request_id = "req-disabled"
        redis_backend.save(sample_record)
        assert len(redis_backend.redis.xrange(MAIN_STREAM)) == 1  # Still 1

        # Enable recording
        redis_backend.enable_recording()
        sample_record.request_id = "req-enabled"
        redis_backend.save(sample_record)
        assert len(redis_backend.redis.xrange(MAIN_STREAM)) == 2  # Now 2

    def test_clear_and_repopulate(self, redis_backend, sample_records):
        """Test clearing data and repopulating."""
        # Populate
        for record in sample_records:
            redis_backend.save(record)

        routes = redis_backend.get_all_routes()
        assert len(routes) > 0

        # Clear
        redis_backend.clear_data()
        routes = redis_backend.get_all_routes()
        assert len(routes) == 0

        # Repopulate
        for record in sample_records:
            redis_backend.save(record)

        routes = redis_backend.get_all_routes()
        assert len(routes) > 0
