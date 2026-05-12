"""
Views for manually triggering and monitoring LabWin sync.
"""

import logging

from celery.result import AsyncResult
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrLabManager

logger = logging.getLogger(__name__)


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
        full_sync = request.data.get("full_sync", False)

        task = sync_labwin_results.delay(
            lab_client_id=lab_client_id,
            full_sync=full_sync,
        )
        logger.info(
            "LabWin sync triggered manually — task_id=%s lab_client_id=%s "
            "full_sync=%s by_user_pk=%s",
            task.id,
            lab_client_id,
            full_sync,
            request.user.pk,
        )

        return Response(
            {
                "message": "Sync task queued successfully.",
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class TriggerFTPFetchView(APIView):
    """
    Trigger a manual FTP PDF fetch (admin and lab staff only).

    POST /api/v1/labwin-sync/fetch-pdfs/
    Returns task_id to track progress.
    """

    permission_classes = [IsAdminOrLabManager]

    def post(self, request):
        from .tasks import fetch_ftp_pdfs

        lab_client_id = request.user.lab_client_id or 1
        delete_after = request.data.get("delete_after_download", False)

        task = fetch_ftp_pdfs.delay(
            lab_client_id=lab_client_id,
            delete_after_download=delete_after,
        )
        logger.info(
            "FTP PDF fetch triggered manually — task_id=%s lab_client_id=%s "
            "delete_after_download=%s by_user_pk=%s",
            task.id,
            lab_client_id,
            delete_after,
            request.user.pk,
        )

        return Response(
            {
                "message": "FTP PDF fetch task queued successfully.",
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class TriggerImportProtocolView(APIView):
    """
    Trigger an on-demand import of ONE LabWin protocol by NUMERO_FLD
    (admin and lab staff only). Used for studies older than the
    nightly 90-day window — patient calls in asking for an old study,
    admin types the protocol number into the UI, this kicks off
    `import_protocol_by_numero` and returns a task_id to poll via the
    existing /labwin-sync/status/<task_id>/ endpoint.

    POST /api/v1/labwin-sync/import-protocol/
        body: { "numero": <int> }
    """

    permission_classes = [IsAdminOrLabManager]

    def post(self, request):
        from .tasks import import_protocol_by_numero

        raw = request.data.get("numero")
        # Accept str or int from JSON; reject anything that doesn't
        # parse as a positive integer.
        try:
            numero = int(raw)
        except (TypeError, ValueError):
            return Response(
                {"error": "numero must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if numero < 1 or numero > 99_999_999:
            return Response(
                {"error": "numero out of range (1..99_999_999)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lab_client_id = request.user.lab_client_id or 1
        # `force` lets the admin bypass the derivacion_skipped filter
        # (walk-in patients with NUMMEDICO_FLD=175). All other filters
        # still apply. Defaults to False — explicit second click only.
        force = bool(request.data.get("force", False))

        task = import_protocol_by_numero.delay(numero, lab_client_id, force=force)
        logger.info(
            "import_protocol_by_numero triggered — task_id=%s numero=%s "
            "lab_client_id=%s force=%s by_user_pk=%s",
            task.id,
            numero,
            lab_client_id,
            force,
            request.user.pk,
        )

        return Response(
            {
                "message": "Import task queued successfully.",
                "task_id": task.id,
                "numero": numero,
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
