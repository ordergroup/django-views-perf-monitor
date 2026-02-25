import contextlib
from dataclasses import dataclass
from datetime import datetime

from django.http import HttpRequest


def _parse_date_range(request: HttpRequest) -> tuple[datetime | None, datetime | None]:
    """Parse since/until date range from request GET parameters."""
    since_str = request.GET.get("since", "").strip()
    until_str = request.GET.get("until", "").strip()

    since = None
    until = None

    if since_str:
        with contextlib.suppress(ValueError):
            since = datetime.fromisoformat(since_str)

    if until_str:
        with contextlib.suppress(ValueError):
            until = datetime.fromisoformat(until_str)

    return since, until


@dataclass
class BreakdownFilters:
    """Base filters for breakdown views."""

    route: str = ""
    status_code: int | None = None
    since: datetime | None = None
    until: datetime | None = None
    sort: str = "timestamp"
    order: str = "desc"  # 'asc' or 'desc'

    VALID_SORT_FIELDS = frozenset(
        {
            "timestamp",
            "route",
            "method",
            "status_code",
            "duration",
        }
    )

    @classmethod
    def from_request(cls, request: HttpRequest) -> "BreakdownFilters":
        """Create filters from HTTP request GET parameters."""
        status_code = request.GET.get("status_code", "").strip()
        status_code_int = None
        if status_code:
            try:
                status_code_int = int(status_code)
                # Validate status code range
                if not (100 <= status_code_int <= 599):
                    status_code_int = None
            except ValueError:
                pass

        since, until = _parse_date_range(request)

        sort = request.GET.get("sort", "timestamp")
        if sort not in cls.VALID_SORT_FIELDS:
            sort = "timestamp"

        order = request.GET.get("order", "desc")
        if order not in ("asc", "desc"):
            order = "desc"

        return cls(
            route=request.GET.get("route", "").strip(),
            status_code=status_code_int,
            since=since,
            until=until,
            sort=sort,
            order=order,
        )


@dataclass
class TagBreakdownFilters(BreakdownFilters):
    """Filters for tag breakdown view."""

    tag: str = ""

    @classmethod
    def from_request(cls, request: HttpRequest) -> "TagBreakdownFilters":
        """Create tag breakdown filters from HTTP request GET parameters."""
        base = super().from_request(request)
        return cls(
            tag=request.GET.get("tag", ""),
            route=base.route,
            status_code=base.status_code,
            since=base.since,
            until=base.until,
            sort=base.sort,
            order=base.order,
        )


@dataclass
class RouteBreakdownFilters(BreakdownFilters):
    """Filters for route breakdown view."""

    route: str = ""
    tag: str = ""

    @classmethod
    def from_request(cls, request: HttpRequest) -> "RouteBreakdownFilters":
        """Create route breakdown filters from HTTP request GET parameters."""
        base = super().from_request(request)
        return cls(
            route=request.GET.get("route", ""),
            tag=request.GET.get("tag", "").strip(),
            status_code=base.status_code,
            since=base.since,
            until=base.until,
            sort=base.sort,
            order=base.order,
        )


@dataclass
class StatsFilters:
    """Filters for stats views (tags_stats, routes_stats)."""

    since: datetime | None = None
    until: datetime | None = None
    sort: str = "avg"

    VALID_SORT_FIELDS = frozenset({"avg", "count"})

    @classmethod
    def from_request(cls, request: HttpRequest) -> "StatsFilters":
        """Create stats filters from HTTP request GET parameters."""
        since, until = _parse_date_range(request)

        sort = request.GET.get("sort", "avg")
        if sort not in cls.VALID_SORT_FIELDS:
            sort = "avg"

        return cls(
            since=since,
            until=until,
            sort=sort,
        )


@dataclass
class RouteTagBreakdownFilters:
    """Filters for route-tag breakdown view."""

    since: datetime | None = None
    until: datetime | None = None
    exclude_untagged: bool = False

    @classmethod
    def from_request(cls, request: HttpRequest) -> "RouteTagBreakdownFilters":
        """Create route-tag breakdown filters from HTTP request GET parameters."""
        since, until = _parse_date_range(request)
        exclude_untagged = request.GET.get("exclude_untagged", "").lower() in (
            "true",
            "1",
            "yes",
        )

        return cls(
            since=since,
            until=until,
            exclude_untagged=exclude_untagged,
        )
