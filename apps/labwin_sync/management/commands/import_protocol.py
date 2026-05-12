"""
Management command to import ONE LabWin protocol by NUMERO_FLD.

CLI fallback for the on-demand import feature when the UI / Celery /
Redis are unavailable. Calls the same task as the API endpoint, just
synchronously and pretty-printed.

Usage:
    python manage.py import_protocol 257008
    python manage.py import_protocol 257008 --lab-client-id 1
    python manage.py import_protocol 257008 --use-celery
"""

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import one LabWin protocol by NUMERO_FLD (on-demand path)."

    def add_arguments(self, parser):
        parser.add_argument(
            "numero",
            type=int,
            help="LabWin NUMERO_FLD (the protocol number).",
        )
        parser.add_argument(
            "--lab-client-id",
            type=int,
            default=None,
            help="Lab client ID to assign to the imported records.",
        )
        parser.add_argument(
            "--use-celery",
            action="store_true",
            help="Queue via Celery worker instead of running synchronously.",
        )

    def handle(self, *args, **options):
        from apps.labwin_sync.tasks import import_protocol_by_numero

        numero = options["numero"]
        lab_client_id = options["lab_client_id"]

        if options["use_celery"]:
            task = import_protocol_by_numero.delay(numero, lab_client_id)
            self.stdout.write(
                self.style.SUCCESS(f"Task submitted to Celery: {task.id}")
            )
            return

        self.stdout.write(
            f"Importing LW-{numero} (synchronous, lab_client_id={lab_client_id})..."
        )
        # bind=True on the task means it expects `self` as the first
        # positional arg; .apply() runs the task in-process and binds
        # `self` to a EagerResult / mock task object that supplies the
        # request.id attribute the task accesses via `self.request.id`.
        async_result = import_protocol_by_numero.apply(
            args=[numero], kwargs={"lab_client_id": lab_client_id}
        )
        result = async_result.result
        self.stdout.write(json.dumps(result, indent=2, default=str))
