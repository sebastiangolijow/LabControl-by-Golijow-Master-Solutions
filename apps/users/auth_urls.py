"""
Custom authentication URL configuration with enhanced security.

This module overrides default dj-rest-auth URLs to apply
custom throttling and security features.
"""

from django.urls import include, path

from .auth_views import LoginView, PasswordResetView, RegistrationView

urlpatterns = [
    # Custom throttled login endpoint
    path("login/", LoginView.as_view(), name="rest_login"),
    # Custom throttled password reset endpoint
    path("password/reset/", PasswordResetView.as_view(), name="rest_password_reset"),
    # Include remaining dj-rest-auth endpoints (logout, password change, etc.)
    path("", include("dj_rest_auth.urls")),
    # Custom throttled registration endpoint
    path("registration/", RegistrationView.as_view(), name="rest_register"),
    # Include remaining registration endpoints (verify email, etc.)
    path("registration/", include("dj_rest_auth.registration.urls")),
]
