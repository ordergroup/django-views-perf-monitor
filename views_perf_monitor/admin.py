import inspect

from django.urls import path, reverse

from views_perf_monitor.views import (
    clear_data_view,
    dashboard_view,
    route_breakdown_view,
    route_x_tag_breakdown_view,
    routes_stats_view,
    tag_breakdown_view,
    tags_stats_view,
    toggle_recording_view,
)


def patch_admin_site(site):
    _orig_get_urls = site.get_urls
    _orig_get_app_list = site.get_app_list

    def new_get_urls():
        custom_urls = [
            path(
                "views-perf-monitor/",
                site.admin_view(lambda req: dashboard_view(req, site)),
                name="views_perf_monitor_dashboard",
            ),
            path(
                "views-perf-monitor/route-tag-breakdown/",
                site.admin_view(lambda req: route_x_tag_breakdown_view(req, site)),
                name="views_perf_route_x_tag_breakdown",
            ),
            path(
                "views-perf-monitor/routes-stats/",
                site.admin_view(lambda req: routes_stats_view(req, site)),
                name="views_perf_routes_stats",
            ),
            path(
                "views-perf-monitor/tags-stats/",
                site.admin_view(lambda req: tags_stats_view(req, site)),
                name="views_perf_tags_stats",
            ),
            path(
                "views-perf-monitor/tag/",
                site.admin_view(lambda req: tag_breakdown_view(req, site)),
                name="views_perf_monitor_tag",
            ),
            path(
                "views-perf-monitor/route/",
                site.admin_view(lambda req: route_breakdown_view(req, site)),
                name="views_perf_monitor_route",
            ),
            path(
                "views-perf-monitor/toggle-recording/",
                site.admin_view(lambda req: toggle_recording_view(req, site)),
                name="views_perf_monitor_toggle_recording",
            ),
            path(
                "views-perf-monitor/clear-data/",
                site.admin_view(lambda req: clear_data_view(req, site)),
                name="views_perf_monitor_clear_data",
            ),
        ]
        return custom_urls + _orig_get_urls()

    site.get_urls = new_get_urls

    _orig_supports_app_label = (
        "app_label" in inspect.signature(_orig_get_app_list).parameters
    )

    def new_get_app_list(request, app_label=None):
        if _orig_supports_app_label:
            app_list = _orig_get_app_list(request, app_label=app_label)
        else:
            app_list = _orig_get_app_list(request)
        if app_label is None or app_label == "views_perf_monitor":
            dashboard_url = reverse(f"{site.name}:views_perf_monitor_dashboard")

            models = [
                {
                    "name": "Dashboard",
                    "object_name": "DjangoViewsPerfDashboard",
                    "admin_url": dashboard_url,
                    "view_only": True,
                },
                {
                    "name": "Route x Tag Breakdown",
                    "object_name": "DjangoViewsPerfRouteXTagBreakdown",
                    "admin_url": reverse(
                        f"{site.name}:views_perf_route_x_tag_breakdown"
                    ),
                    "view_only": True,
                },
                {
                    "name": "Routes Statistics",
                    "object_name": "DjangoViewRoutesStats",
                    "admin_url": reverse(f"{site.name}:views_perf_routes_stats"),
                    "view_only": True,
                },
                {
                    "name": "Tags Statistics",
                    "object_name": "DjangoViewsTagsStats",
                    "admin_url": reverse(f"{site.name}:views_perf_tags_stats"),
                    "view_only": True,
                },
            ]

            app_list.append(
                {
                    "name": "Django Views Perf Monitor",
                    "app_label": "views_perf_monitor",
                    "app_url": dashboard_url,
                    "has_module_perms": True,
                    "models": models,
                }
            )
        return app_list

    site.get_app_list = new_get_app_list
