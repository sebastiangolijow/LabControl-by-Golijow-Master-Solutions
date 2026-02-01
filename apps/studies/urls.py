"""URL configuration for studies app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PracticeViewSet, StudyTypeViewSet, StudyViewSet

router = DefaultRouter()
router.register(r"practices", PracticeViewSet, basename="practice")
router.register(r"types", StudyTypeViewSet, basename="study-type")
router.register(r"", StudyViewSet, basename="study")

app_name = "studies"

urlpatterns = [
    path("", include(router.urls)),
]
