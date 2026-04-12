"""URL configuration for users app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ImportDoctorsView,
    PatientRegistrationView,
    ResendVerificationEmailView,
    SetPasswordView,
    UserViewSet,
    VerifyEmailView,
)

router = DefaultRouter()
router.register(r"", UserViewSet, basename="user")

app_name = "users"

urlpatterns = [
    path("register/", PatientRegistrationView.as_view(), name="patient-register"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("set-password/", SetPasswordView.as_view(), name="set-password"),
    path(
        "resend-verification/",
        ResendVerificationEmailView.as_view(),
        name="resend-verification",
    ),
    path("import-doctors/", ImportDoctorsView.as_view(), name="import-doctors"),
    path("", include(router.urls)),
]
