"""URL configuration for studies app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DeterminationViewSet,
    PracticeViewSet,
    StudyViewSet,
    UserDeterminationViewSet,
)

router = DefaultRouter()
router.register(r"practices", PracticeViewSet, basename="practice")
router.register(r"determinations", DeterminationViewSet, basename="determination")
router.register(
    r"user-determinations", UserDeterminationViewSet, basename="user-determination"
)
router.register(r"", StudyViewSet, basename="study")

app_name = "studies"

urlpatterns = [
    path("", include(router.urls)),
]
