"""URL configuration for LabWin sync app."""

from django.urls import path

from . import views

urlpatterns = [
    path("trigger/", views.TriggerSyncView.as_view(), name="labwin-sync-trigger"),
    path(
        "fetch-pdfs/",
        views.TriggerFTPFetchView.as_view(),
        name="labwin-ftp-fetch",
    ),
    path(
        "import-protocol/",
        views.TriggerImportProtocolView.as_view(),
        name="labwin-import-protocol",
    ),
    path(
        "status/<str:task_id>/",
        views.SyncStatusView.as_view(),
        name="labwin-sync-status",
    ),
]
