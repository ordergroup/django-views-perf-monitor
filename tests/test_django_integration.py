"""
Django integration tests for views_perf_monitor.

Tests the full Django middleware integration with the Redis backend,
simulating real HTTP requests and verifying that performance data is
correctly captured and stored.
"""

import time
from unittest.mock import patch

import django
import fakeredis
import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path, resolve
from redis import Redis

from views_perf_monitor.backends import PerformanceRecordQueryBuilder
from views_perf_monitor.backends.redis import RedisBackend
from views_perf_monitor.middleware import perf_middleware


# Test views
def simple_view(request):
    """A simple test view that returns 200."""
    return HttpResponse("OK", status=200)


def slow_view(request):
    """A view that takes some time."""
    time.sleep(0.01)  # 10ms
    return HttpResponse("Slow OK", status=200)


def error_view(request):
    """A view that returns an error."""
    return HttpResponse("Not Found", status=404)


def api_view(request):
    """An API view."""
    return HttpResponse('{"status": "ok"}', status=200, content_type="application/json")


# URL patterns for testing
urlpatterns = [
    path("test/simple/", simple_view, name="simple"),
    path("test/slow/", slow_view, name="slow"),
    path("test/error/", error_view, name="error"),
    path("api/v1/users/", api_view, name="api-users"),
]


# Test settings configuration
TEST_SETTINGS = {
    "INSTALLED_APPS": [
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "django.contrib.admin",
        "views_perf_monitor",
    ],
    "MIDDLEWARE": [
        "django.middleware.security.SecurityMiddleware",
        "django.middleware.common.CommonMiddleware",
        "views_perf_monitor.middleware.perf_middleware",
    ],
    "ROOT_URLCONF": "tests.test_django_integration",
    "SECRET_KEY": "test-secret-key",
    "VIEWS_PERF_MONITOR_BACKEND": {
        "backend": "views_perf_monitor.backends.redis.RedisBackend",
        "kwargs": {
            "redis_url": "redis://localhost:6379/0",
            "ttl_days": 30,
        },
    },
    "DATABASES": {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    },
}


# Configure Django for testing
if not settings.configured:
    settings.configure(**TEST_SETTINGS)
    django.setup()


@pytest.fixture
def redis_backend(fake_redis):
    """Create a Redis backend with fake Redis for testing."""
    with patch.object(Redis, "from_url", return_value=fake_redis):
        backend = RedisBackend(
            redis_url="redis://localhost:6379/0",
            ttl_days=30,
            max_stream_length=1000,
            cache_ttl_seconds=300,
        )
        yield backend


@pytest.fixture
def fake_redis():
    """Create a fake Redis instance."""
    server = fakeredis.FakeServer()
    return fakeredis.FakeStrictRedis(server=server, decode_responses=True)


@pytest.fixture
def middleware(redis_backend):
    """Create the performance middleware with fake backend."""

    def dummy_get_response(request):
        """Resolve the request and call the view."""

        # Resolve the URL and attach resolver_match to request
        resolver_match = resolve(request.path)
        request.resolver_match = resolver_match

        # Call the view
        return resolver_match.func(request)

    with patch(
        "views_perf_monitor.middleware.get_performance_monitor_backend",
        return_value=redis_backend,
    ):
        return perf_middleware(dummy_get_response)


@pytest.fixture
def request_factory():
    """Create a Django request factory."""
    return RequestFactory()


class TestDjangoMiddlewareIntegration:
    """Test Django middleware integration with Redis backend."""

    def test_middleware_captures_simple_request(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware captures a simple successful request."""
        # Create a request
        request = request_factory.get("/test/simple/")

        # Process through middleware
        response = middleware(request)

        # Verify response
        assert response.status_code == 200
        assert response.content == b"OK"

        # Verify data was saved to backend
        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 1
        record = records[0]
        assert record.route == "/test/simple/"
        assert record.status_code == 200
        assert record.method == "GET"
        assert record.duration > 0
        assert record.request_id is not None

    def test_middleware_captures_slow_request(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware accurately measures duration of slow requests."""
        request = request_factory.get("/test/slow/")

        response = middleware(request)

        assert response.status_code == 200

        # Check that duration was measured
        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 1
        record = records[0]
        assert record.duration >= 0.01  # Should be at least 10ms
        assert record.route == "/test/slow/"

    def test_middleware_captures_error_response(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware captures error responses."""
        request = request_factory.get("/test/error/")

        response = middleware(request)

        assert response.status_code == 404

        # Verify error was recorded
        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 1
        record = records[0]
        assert record.status_code == 404
        assert record.route == "/test/error/"

    def test_middleware_applies_default_tags(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware applies default tags based on path."""
        # API request should get 'api' tag
        request = request_factory.get("/api/v1/users/")
        response = middleware(request)

        assert response.status_code == 200

        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 1
        record = records[0]
        assert "api" in record.tags
        assert record.route == "/api/v1/users/"

    def test_middleware_captures_multiple_requests(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware captures multiple requests correctly."""
        # Make several requests
        paths = ["/test/simple/", "/test/slow/", "/test/error/", "/api/v1/users/"]

        for request_path in paths:
            request = request_factory.get(request_path)
            middleware(request)

        # Verify all were recorded
        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 4

        # Check that we have records for all routes
        routes = {r.route for r in records}
        assert routes == {
            "/test/simple/",
            "/test/slow/",
            "/test/error/",
            "/api/v1/users/",
        }

    def test_middleware_captures_different_methods(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware captures different HTTP methods."""
        methods = ["GET", "POST", "PUT", "DELETE"]

        for method in methods:
            factory_method = getattr(request_factory, method.lower())
            request = factory_method("/test/simple/")
            middleware(request)

        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)

        assert len(records) == 4

        # Check that all methods were recorded
        recorded_methods = {r.method for r in records}
        assert recorded_methods == set(methods)

    def test_middleware_aggregates_route_stats(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware properly aggregates statistics for routes."""
        # Make multiple requests to the same route
        for _ in range(5):
            request = request_factory.get("/test/simple/")
            middleware(request)

        # Get route statistics
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_routes_stats(query)

        assert len(stats) == 1
        route_stat = stats[0]
        assert route_stat.route == "/test/simple/"
        assert route_stat.count == 5
        assert route_stat.avg > 0
        assert route_stat.error_count == 0

    def test_middleware_tracks_errors_in_stats(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware tracks errors in route statistics."""
        # Mix of successful and error requests
        for _ in range(3):
            request = request_factory.get("/test/simple/")
            middleware(request)

        for _ in range(2):
            request = request_factory.get("/test/error/")
            middleware(request)

        # Check route stats
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_routes_stats(query)

        assert len(stats) == 2

        # Find error route stats
        error_stat = next(s for s in stats if s.route == "/test/error/")
        assert error_stat.count == 2
        assert error_stat.error_count == 2
        assert error_stat.error_rate == 100.0

        # Find success route stats
        success_stat = next(s for s in stats if s.route == "/test/simple/")
        assert success_stat.count == 3
        assert success_stat.error_count == 0
        assert success_stat.error_rate == 0.0

    def test_middleware_tags_stats(self, middleware, request_factory, redis_backend):
        """Test that middleware properly tracks tag statistics."""
        # Make API requests
        for _ in range(3):
            request = request_factory.get("/api/v1/users/")
            middleware(request)

        # Get tag statistics
        query = PerformanceRecordQueryBuilder.all()
        stats = redis_backend.get_tags_stats(query)

        assert len(stats) == 1
        tag_stat = stats[0]
        assert tag_stat.tag == "api"
        assert tag_stat.count == 3
        assert tag_stat.avg > 0

    def test_middleware_respects_recording_control(
        self, middleware, request_factory, redis_backend
    ):
        """Test that middleware respects recording enable/disable."""
        # Make a request with recording enabled
        request = request_factory.get("/test/simple/")
        middleware(request)

        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)
        assert len(records) == 1

        # Disable recording
        redis_backend.disable_recording()

        # Make another request - should not be recorded
        request = request_factory.get("/test/simple/")
        middleware(request)

        # Clear the cache before fetching to ensure fresh results
        redis_backend.redis.delete(redis_backend._get_cache_key("fetch", query))

        # Should still only have 1 record
        records = redis_backend.fetch(query)
        assert len(records) == 1

        # Re-enable recording
        redis_backend.enable_recording()

        # Make another request - should be recorded
        request = request_factory.get("/test/simple/")
        middleware(request)

        # Clear the cache again
        redis_backend.redis.delete(redis_backend._get_cache_key("fetch", query))

        # Should now have 2 records
        records = redis_backend.fetch(query)
        assert len(records) == 2


class TestMiddlewareIntegrationWithRealScenarios:
    """Test middleware with realistic usage scenarios."""

    def test_mixed_api_and_regular_requests(
        self, middleware, request_factory, redis_backend
    ):
        """Test a realistic mix of API and regular requests."""
        # Simulate a realistic workload
        requests_to_make = [
            ("/api/v1/users/", "GET", 3),
            ("/test/simple/", "GET", 5),
            ("/test/error/", "GET", 2),
            ("/api/v1/users/", "POST", 2),
        ]

        for request_path, method, count in requests_to_make:
            for _ in range(count):
                factory_method = getattr(request_factory, method.lower())
                request = factory_method(request_path)
                middleware(request)

        # Verify total count
        query = PerformanceRecordQueryBuilder.all()
        records = redis_backend.fetch(query)
        assert len(records) == 12  # 3 + 5 + 2 + 2

        # Check route breakdown
        route_stats = redis_backend.get_routes_stats(query)
        assert len(route_stats) == 3

        # Check tag stats (API requests)
        tag_stats = redis_backend.get_tags_stats(query)
        api_stat = next(s for s in tag_stats if s.tag == "api")
        assert api_stat.count == 5  # 3 GET + 2 POST to API

    def test_request_trend_tracking(self, middleware, request_factory, redis_backend):
        """Test that request trends are tracked properly."""
        # Make several requests
        for _ in range(10):
            request = request_factory.get("/test/simple/")
            middleware(request)

        # Check request trend
        query = PerformanceRecordQueryBuilder.all()
        trend = redis_backend.request_trend(query)

        # Should have at least one hour bucket with 10 requests
        assert len(trend) >= 1
        assert sum(trend.values()) == 10

    def test_status_code_distribution(self, middleware, request_factory, redis_backend):
        """Test status code distribution tracking."""
        # Create various status codes
        status_paths = [
            ("/test/simple/", 200, 5),
            ("/test/error/", 404, 3),
        ]

        for request_path, _expected_status, count in status_paths:
            for _ in range(count):
                request = request_factory.get(request_path)
                middleware(request)

        # Check status code stats
        query = PerformanceRecordQueryBuilder.all()
        status_stats = redis_backend.status_code_stats(query)

        # Should have 2xx and 4xx
        groups = {s.group for s in status_stats}
        assert "2xx" in groups
        assert "4xx" in groups

        # Check counts
        status_200 = next(s for s in status_stats if s.status_code == 200)
        assert status_200.count == 5

        status_404 = next(s for s in status_stats if s.status_code == 404)
        assert status_404.count == 3
