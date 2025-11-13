import logging
from pathlib import Path
from typing import Optional

from celery import shared_task

from .models import UploadJob

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="products.import_csv_task")
def import_csv_task(self, upload_task_id: str, file_path: str, user_id: Optional[int] = None) -> None:
    """Stub task for importing CSV files."""
    logger.info(
        "Received import_csv_task task_id=%s file_path=%s user_id=%s",
        upload_task_id,
        file_path,
        user_id,
    )

    job = UploadJob.objects.filter(task_id=upload_task_id).first()
    if not job:
        logger.warning("UploadJob with task_id=%s not found.", upload_task_id)
        return

    job.status = UploadJob.Status.IN_PROGRESS
    job.save(update_fields=["status", "updated_at"])

    try:
        # TODO: Implement CSV parsing and product import logic
        file_exists = Path(file_path).exists()
        logger.debug("File exists: %s", file_exists)

        job.status = UploadJob.Status.COMPLETED
        job.processed_rows = job.total_rows or 0
        job.save(update_fields=["status", "processed_rows", "updated_at"])
    except Exception as exc:  # pragma: no cover - protective logging
        logger.exception("Failed to process upload %s", upload_task_id)
        job.status = UploadJob.Status.FAILED
        job.errors_json = [{"message": str(exc)}]
        job.save(update_fields=["status", "errors_json", "updated_at"])
        raise

