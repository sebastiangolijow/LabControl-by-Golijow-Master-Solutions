"""
Views for manually triggering and monitoring LabWin sync.
"""

from celery.result import AsyncResult
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrLabManager


class TriggerSyncView(APIView):
    """
    Trigger a manual LabWin sync (admin and lab staff only).

    POST /api/v1/labwin-sync/trigger/
    Returns task_id to track sync progress.
    """

    permission_classes = [IsAdminOrLabManager]

    def post(self, request):
        from .tasks import sync_labwin_results

        lab_client_id = request.user.lab_client_id or 1

        task = sync_labwin_results.delay(
            lab_client_id=lab_client_id,
            full_sync=request.data.get("full_sync", False),
        )

        return Response(
            {
                "message": "Sync task queued successfully.",
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SyncStatusView(APIView):
    """
    Check status of a LabWin sync task.

    GET /api/v1/labwin-sync/status/<task_id>/
    """

    permission_classes = [IsAdminOrLabManager]

    def get(self, request, task_id):
        task = AsyncResult(task_id)

        if task.state == "PENDING":
            response = {
                "state": task.state,
                "status": "Task is waiting to be processed...",
            }
        elif task.state == "PROCESSING":
            info = task.info or {}
            response = {
                "state": task.state,
                "status": "Syncing...",
                "processed": info.get("processed", 0),
                "patients_created": info.get("patients_created", 0),
                "studies_created": info.get("studies_created", 0),
                "studies_updated": info.get("studies_updated", 0),
                "errors": info.get("errors", 0),
            }
        elif task.state == "SUCCESS":
            response = {
                "state": task.state,
                "status": "Sync completed",
                "result": task.info,
            }
        elif task.state == "FAILURE":
            response = {
                "state": task.state,
                "status": "Sync failed",
                "error": str(task.info),
            }
        else:
            response = {
                "state": task.state,
                "status": str(task.info),
            }

        return Response(response)
