"""
URL configuration for LabControl platform.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
"""

import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework import routers

# API Router
router = routers.DefaultRouter()
# Register your viewsets here
# Example: router.register(r'users', UserViewSet)

# Security: Custom admin URL from environment variable
# Default to 'admin/' in development, but should be changed in production
ADMIN_URL = os.getenv("ADMIN_URL", "admin/")

urlpatterns = [
    # Admin panel (customizable URL for security)
    path(ADMIN_URL, admin.site.urls),
    # API endpoints
    path(
        "api/v1/",
        include(
            [
                # API root
                path("", include(router.urls)),
                # Authentication endpoints (custom throttled views)
                path("auth/", include("apps.users.auth_urls")),
                # App-specific endpoints
                path("users/", include("apps.users.urls")),
                path("studies/", include("apps.studies.urls")),
                path("appointments/", include("apps.appointments.urls")),
                path("payments/", include("apps.payments.urls")),
                path("notifications/", include("apps.notifications.urls")),
                path("analytics/", include("apps.analytics.urls")),
            ]
        ),
    ),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

# Development-specific URLs
if settings.DEBUG:
    # Django Debug Toolbar
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
    ]
    # Serve media files in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Customize admin site
admin.site.site_header = "LabControl Administration"
admin.site.site_title = "LabControl Admin"
admin.site.index_title = "Welcome to LabControl Admin Panel"
