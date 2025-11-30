"""URL configuration for users app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PatientRegistrationView, UserViewSet

router = DefaultRouter()
router.register(r"", UserViewSet, basename="user")

app_name = "users"

urlpatterns = [
    path("register/", PatientRegistrationView.as_view(), name="patient-register"),
    path("", include(router.urls)),
]
