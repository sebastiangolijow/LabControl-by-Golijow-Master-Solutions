"""Celery tasks for users app."""

import csv
import io
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def import_doctors_task(self, csv_content, lab_client_id=None):
    """
    Import doctors from CSV file asynchronously.

    Args:
        csv_content: String content of the CSV file
        lab_client_id: Optional lab client ID to assign to created doctors

    Returns:
        dict: Summary with created, skipped, and errors counts
    """
    from apps.users.models import User

    try:
        # Update task state to show progress
        self.update_state(state='PROCESSING', meta={'status': 'Starting import...'})

        csv_reader = csv.DictReader(io.StringIO(csv_content))

        created_count = 0
        skipped_count = 0
        errors = []
        total_rows = 0

        for row_number, row in enumerate(csv_reader, start=2):
            total_rows += 1

            # Update progress every 100 rows
            if total_rows % 100 == 0:
                self.update_state(
                    state='PROCESSING',
                    meta={
                        'status': f'Processing row {total_rows}...',
                        'processed': total_rows,
                        'created': created_count,
                        'skipped': skipped_count,
                        'errors': len(errors)
                    }
                )

            try:
                # Extract data from row
                nombre_medico = row.get("NOMBRE_MEDICO", "").strip()
                matricula_raw = row.get("MATRICULA_O_ID", "").strip()

                # Skip empty rows
                if not nombre_medico or not matricula_raw:
                    continue

                # Parse matricula
                matricula = str(matricula_raw)

                # Check if doctor with this matricula already exists
                if User.objects.filter(matricula=matricula).exists():
                    skipped_count += 1
                    continue

                # Parse name into first_name and last_name
                first_name, last_name = _parse_name(nombre_medico)

                # Create doctor user
                user = User.objects.create_user(
                    first_name=first_name,
                    last_name=last_name,
                    matricula=matricula,
                    role="doctor",
                    is_active=True,
                    is_verified=True,
                )

                # Set lab_client_id if provided
                if lab_client_id:
                    user.lab_client_id = lab_client_id
                    user.save(update_fields=["lab_client_id"])

                created_count += 1

            except Exception as e:
                error_msg = str(e)
                errors.append({
                    "row": row_number,
                    "error": error_msg,
                    "name": nombre_medico if "nombre_medico" in locals() else "Unknown",
                })
                logger.error(f"Error importing doctor at row {row_number}: {error_msg}")

        # Final result
        result = {
            "message": f"Import completed. Created: {created_count}, Skipped: {skipped_count}, Errors: {len(errors)}",
            "created": created_count,
            "skipped": skipped_count,
            "errors": errors,
            "total_processed": total_rows
        }

        logger.info(f"Doctor import completed: {result['message']}")
        return result

    except Exception as e:
        error_msg = f"Failed to process CSV file: {str(e)}"
        logger.error(error_msg)
        self.update_state(
            state='FAILURE',
            meta={'error': error_msg}
        )
        raise


def _parse_name(full_name):
    """
    Parse full name into first_name and last_name.

    Formats handled:
    - "Last, First" -> first_name="First", last_name="Last"
    - "First Last" -> first_name="First", last_name="Last"
    - "Single" -> first_name="Single", last_name=""
    """
    full_name = full_name.strip()

    # Check if comma-separated (Last, First format)
    if "," in full_name:
        parts = full_name.split(",", 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ""
        return first_name, last_name

    # Check if space-separated
    if " " in full_name:
        parts = full_name.split(None, 1)
        first_name = parts[0].strip()
        last_name = parts[1].strip() if len(parts) > 1 else ""
        return first_name, last_name

    # Single name only
    return full_name, ""
