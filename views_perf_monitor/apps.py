from django.apps import AppConfig


class DjangoViewsPerfMonitor(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "views_perf_monitor"
    verbose_name = "Views Performance Monitor"

    def ready(self):
        from django.contrib import admin

        from .admin import patch_admin_site

        patch_admin_site(admin.site)
