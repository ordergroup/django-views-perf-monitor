from django.urls import path, reverse

from views_perf_monitor.views import dashboard_view, route_breakdown_view, tag_breakdown_view


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
                "views-perf-monitor/tag/",
                site.admin_view(lambda req: tag_breakdown_view(req, site)),
                name="views_perf_monitor_tag",
            ),
            path(
                "views-perf-monitor/route/",
                site.admin_view(lambda req: route_breakdown_view(req, site)),
                name="views_perf_monitor_route",
            ),
        ]
        return custom_urls + _orig_get_urls()

    site.get_urls = new_get_urls

    def new_get_app_list(request, app_label=None):
        app_list = _orig_get_app_list(request, app_label=app_label)
        if app_label is None or app_label == "views_perf_monitor":
            dashboard_url = reverse(f"{site.name}:views_perf_monitor_dashboard")

            models = [
                {
                    "name": "Dashboard",
                    "object_name": "DjangoViewsPerfDashboard",
                    "admin_url": dashboard_url,
                    "view_only": True,
                }
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


