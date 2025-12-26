"""URL configuration for users app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PatientRegistrationView,
    ResendVerificationEmailView,
    UserViewSet,
    VerifyEmailView,
)

router = DefaultRouter()
router.register(r"", UserViewSet, basename="user")

app_name = "users"

urlpatterns = [
    path("register/", PatientRegistrationView.as_view(), name="patient-register"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path(
        "resend-verification/",
        ResendVerificationEmailView.as_view(),
        name="resend-verification",
    ),
    path("", include(router.urls)),
]
