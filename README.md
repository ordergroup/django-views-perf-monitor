# django-views-perf-monitor

A Django middleware that tracks HTTP request performance and surfaces it as a dashboard inside Django Admin.

## Features

- Per-request timing, route, method, status code, and tags
- Pluggable storage backends (Redis included; Dummy no-op default)
- Interactive charts and sortable tables in the Django Admin
- Configurable tag and request ID extraction via callables

---

## Installation

### Using uv (recommended)

```bash
uv add git+https://github.com/ordergroup/django-views-perf-monitor.git
```

### 1. Add to `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    # ...
    "views_perf_monitor",
]
```

### 2. Add the middleware

```python
MIDDLEWARE = [
    # ...
    "views_perf_monitor.middleware.perf_middleware",
]
```

### 3. Configure a backend

By default the **Dummy** backend is used, which discards all data. Switch to Redis to persist records:

```python
VIEWS_PERF_MONITOR_BACKEND = {
    "backend": "views_perf_monitor.backends.redis.RedisBackend",
    "kwargs": {
        "redis_url": "redis://localhost:6379/0",
        "ttl_days": 30,
    },
}
```

---

## Configuration

### `VIEWS_PERF_REQUEST_TAGS_CALLABLE`

A callable that receives an `HttpRequest` and returns a `list[str]` of tags for the request. Used to group requests in the dashboard.

**Default behaviour:**

```python
def default_get_request_tags(request):
    if "/api" in request.path:
        return ["api"]
    if "/admin" in request.path:
        return ["admin"]
    return []
```

**Custom example — tag by authenticated user and API version:**

```python
# myapp/perf.py
def get_request_tags(request):
    tags = []
    if request.path.startswith("/api/v1/"):
        tags.append("api_v1")
    elif request.path.startswith("/api/v2/"):
        tags.append("api_v2")
    if hasattr(request, "user") and request.user.is_authenticated:
        tags.append("authenticated")
    return tags
```

```python
# settings.py
from myapp.perf import get_request_tags

VIEWS_PERF_REQUEST_TAGS_CALLABLE = get_request_tags
```

### `VIEWS_PERF_REQUEST_ID_CALLABLE`

A callable that receives an `HttpRequest` and returns a `str` to use as the unique request identifier.

**Default behaviour:** generates a random `uuid4()` per request.

**Custom example — propagate an upstream `X-Request-ID` header:**

```python
# myapp/perf.py
def get_request_id(request):
    header = request.headers.get("X-Request-Id")
    if header:
        try:
            return header
        except ValueError:
            pass
    return uuid4()
```

```python
# settings.py
from myapp.perf import get_request_id

VIEWS_PERF_REQUEST_ID_CALLABLE = get_request_id
```

---

## Requirements

- Python 3.12+
- Django 4.2+
- Redis (only when using `RedisBackend`)
