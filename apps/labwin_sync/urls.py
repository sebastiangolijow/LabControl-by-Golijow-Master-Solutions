"""URL configuration for LabWin sync app."""

from django.urls import path

from . import views

urlpatterns = [
    path("trigger/", views.TriggerSyncView.as_view(), name="labwin-sync-trigger"),
    path(
        "status/<str:task_id>/",
        views.SyncStatusView.as_view(),
        name="labwin-sync-status",
    ),
]
