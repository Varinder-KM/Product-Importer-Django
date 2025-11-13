import csv
import logging
import traceback
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional, Tuple

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from psycopg2 import sql

from webhooks.models import Webhook
from webhooks.tasks import queue_event

from .models import DeletionJob, Product, UploadJob
from .utils.csv_batch_loader import CSVBatchLoader
logger = logging.getLogger(__name__)

_channel_layer = None

ProgressPayload = Dict[str, Optional[object]]

TRUTHY_VALUES = {"1", "true", "yes", "y", "t"}
MAX_ERROR_RECORDS = 50


def _get_channel_layer():
    global _channel_layer
    if _channel_layer is None:
        _channel_layer = get_channel_layer()
    return _channel_layer


def _calculate_percent(processed: int, total: int) -> int:
    if total <= 0:
        return 100 if processed > 0 else 0
    return min(100, int((processed / total) * 100))


def _publish_progress(
    identifier: str,
    namespace: str,
    event_type: str,
    payload: ProgressPayload,
) -> ProgressPayload:
    try:
        channel_layer = _get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f"{namespace}_{identifier}",
                {"type": event_type, "payload": payload},
            )
    except Exception:
        logger.exception("Failed to publish progress via Channels for %s %s", namespace, identifier)
    return payload


def _write_upload_progress(
    task_id: str,
    *,
    status: str,
    processed: int,
    total: int,
    percent: int,
    errors: int,
    error: Optional[str] = None,
) -> ProgressPayload:
    payload: ProgressPayload = {
        "status": status,
        "processed": processed,
        "total": total,
        "percent": percent,
        "errors": errors,
        "error": error,
    }
    return _publish_progress(task_id, "upload", "upload.progress", payload)


def publish_delete_progress(
    job_id: int,
    *,
    status: str,
    processed: int,
    total: int,
    percent: int,
    errors: int,
    error: Optional[str] = None,
) -> ProgressPayload:
    payload: ProgressPayload = {
        "status": status,
        "processed": processed,
        "total": total,
        "percent": percent,
        "errors": errors,
        "error": error,
    }
    return _publish_progress(str(job_id), "delete", "deletion.progress", payload)


def _normalize_row(
    row_number: int, row: Dict[str, Optional[str]]
) -> Tuple[Optional[Dict[str, object]], Optional[Dict[str, object]]]:
    normalized = {k.lower(): (v or "").strip() for k, v in row.items() if k}

    raw_sku = normalized.get("sku", "")
    if not raw_sku:
        return None, {"row": row_number, "error": "SKU is required."}
    sku = raw_sku
    sku_lower = sku.lower()

    name = normalized.get("name", "")
    description = normalized.get("description", "")

    raw_price = normalized.get("price", "0")
    try:
        price = Decimal(raw_price or "0")
    except InvalidOperation:
        return None, {
            "row": row_number,
            "error": f"Invalid price value '{raw_price}'.",
        }

    raw_active = normalized.get("active", "true").lower()
    active = raw_active in TRUTHY_VALUES

    now_iso = timezone.now().isoformat()

    return (
        {
            "sku": sku,
            "sku_lower": sku_lower,
            "name": name,
            "description": description,
            "price": price,
            "active": active,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        None,
    )


def _copy_batch_to_database(
    batch_rows: List[Dict[str, object]],
    temp_table_name: str,
) -> None:
    if not batch_rows:
        return

    quoted_temp_table = connection.ops.quote_name(temp_table_name)

    with transaction.atomic():
        with connection.cursor() as cursor:
            create_temp_sql = f"""
                CREATE TEMP TABLE {quoted_temp_table} (
                    sku TEXT,
                    sku_lower TEXT,
                    name TEXT,
                    description TEXT,
                    price NUMERIC(10, 2),
                    active BOOLEAN,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ
                ) ON COMMIT DROP;
            """
            cursor.execute(create_temp_sql)

            tmp_path: Optional[Path] = None

            with NamedTemporaryFile("w", newline="", delete=False) as tmp_file:
                writer = csv.writer(tmp_file)
                writer.writerow(
                    [
                        "sku",
                        "sku_lower",
                        "name",
                        "description",
                        "price",
                        "active",
                        "created_at",
                        "updated_at",
                    ]
                )
                for row in batch_rows:
                    price_value = Decimal(row["price"])
                    writer.writerow(
                        [
                            row["sku"],
                            row["sku_lower"],
                            row["name"],
                            row["description"],
                            format(price_value, "f"),
                            "true" if row["active"] else "false",
                            row["created_at"],
                            row["updated_at"],
                        ]
                    )
                tmp_path = Path(tmp_file.name)

            try:
                if tmp_path is None:
                    raise RuntimeError("Temporary file path was not created for batch load.")
                with tmp_path.open("r", newline="") as read_handle:
                    copy_sql = f"""
                        COPY {quoted_temp_table} (sku, sku_lower, name, description, price, active, created_at, updated_at)
                        FROM STDIN WITH CSV HEADER;
                    """
                    cursor.copy_expert(copy_sql, read_handle)

                upsert_sql = f"""
                    INSERT INTO products_product (sku, name, description, price, active, created_at, updated_at)
                    SELECT
                        sku,
                        name,
                        description,
                        price,
                        active,
                        created_at,
                        updated_at
                    FROM {quoted_temp_table}
                    ON CONFLICT ((lower(sku)))
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        price = EXCLUDED.price,
                        active = EXCLUDED.active,
                        updated_at = EXCLUDED.updated_at;
                """
                cursor.execute(upsert_sql)
            finally:
                # Clean up temp file. Temp table will be auto-dropped by ON COMMIT DROP
                try:
                    if tmp_path is not None:
                        tmp_path.unlink(missing_ok=True)
                except FileNotFoundError:
                    pass


@shared_task(bind=True, name="products.import_csv_task")
def import_csv_task(self, upload_task_id: str, file_path: str, user_id: Optional[int] = None) -> None:
    """Import a CSV file of products with batched COPY operations."""
    logger.info(
        "Starting import_csv_task task_id=%s file_path=%s user_id=%s",
        upload_task_id,
        file_path,
        user_id,
    )

    job = UploadJob.objects.filter(task_id=upload_task_id).first()
    if not job:
        logger.warning("UploadJob with task_id=%s not found.", upload_task_id)
        _write_upload_progress(
            upload_task_id,
            status="failed",
            processed=0,
            total=0,
            percent=0,
            errors=0,
            error="Upload job not found.",
        )
        return

    csv_path = Path(file_path)
    if not csv_path.exists():
        error_message = f"CSV file not found at {file_path}"
        logger.error(error_message)
        job.status = UploadJob.Status.FAILED
        job.errors_json = [{"message": error_message}]
        job.save(update_fields=["status", "errors_json", "updated_at"])
        _write_upload_progress(
            upload_task_id,
            status="failed",
            processed=0,
            total=0,
            percent=0,
            errors=1,
            error=error_message,
        )
        return

    batch_size = getattr(settings, "PRODUCT_IMPORT_BATCH_SIZE", 5000)
    loader = CSVBatchLoader(csv_path, batch_size=batch_size)

    job.status = UploadJob.Status.IN_PROGRESS
    job.processed_rows = 0
    job.total_rows = loader.count_rows()
    job.errors_json = []
    job.save(update_fields=["status", "processed_rows", "total_rows", "errors_json", "updated_at"])

    total_rows = job.total_rows or 0
    processed_rows = 0
    error_count = 0
    error_details: List[Dict[str, object]] = []

    logger.info(
        "Upload %s contains %s data rows (batch size %s).",
        upload_task_id,
        total_rows,
        batch_size,
    )

    initial_payload = _write_upload_progress(
        upload_task_id,
        status="in_progress",
        processed=processed_rows,
        total=total_rows,
        percent=0,
        errors=error_count,
    )
    self.update_state(state="PROGRESS", meta=initial_payload)

    try:
        for batch_index, batch in enumerate(loader, start=1):
            normalized_rows: List[Dict[str, object]] = []
            for row_number, row in batch:
                processed_rows += 1
                normalized, error = _normalize_row(row_number, row)
                if error:
                    error_count += 1
                    if len(error_details) < MAX_ERROR_RECORDS:
                        error_details.append(error)
                    continue
                normalized_rows.append(normalized)

            # Deduplicate by SKU (case-insensitive) - keep last occurrence
            # This prevents "ON CONFLICT DO UPDATE cannot affect row a second time" errors
            # when the same batch contains duplicate SKUs
            seen_skus = {}
            for row in normalized_rows:
                sku_lower = row["sku_lower"]
                seen_skus[sku_lower] = row  # Last occurrence wins
            deduplicated_rows = list(seen_skus.values())

            temp_table_name = f"tmp_products_upload_{upload_task_id[:8]}_{batch_index}"
            _copy_batch_to_database(deduplicated_rows, temp_table_name)

            job.processed_rows = processed_rows
            job.errors_json = error_details[:MAX_ERROR_RECORDS]
            job.save(update_fields=["processed_rows", "errors_json", "updated_at"])

            percent = _calculate_percent(processed_rows, total_rows)
            payload = _write_upload_progress(
                upload_task_id,
                status="in_progress",
                processed=processed_rows,
                total=total_rows,
                percent=percent,
                errors=error_count,
            )
            self.update_state(state="PROGRESS", meta=payload)
            queue_event(
                Webhook.EVENT_IMPORT_PROGRESS,
                {
                    "event": Webhook.EVENT_IMPORT_PROGRESS,
                    "task_id": upload_task_id,
                    "batch_index": batch_index,
                    "processed": processed_rows,
                    "total": total_rows,
                    "errors": error_count,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        job.status = UploadJob.Status.COMPLETED
        job.processed_rows = processed_rows
        job.errors_json = error_details
        job.save(update_fields=["status", "processed_rows", "errors_json", "updated_at"])

        final_payload = _write_upload_progress(
            upload_task_id,
            status="completed",
            processed=processed_rows,
            total=total_rows,
            percent=100,
            errors=error_count,
        )
        self.update_state(state="SUCCESS", meta=final_payload)
        queue_event(
            Webhook.EVENT_IMPORT_COMPLETED,
            {
                "event": Webhook.EVENT_IMPORT_COMPLETED,
                "task_id": upload_task_id,
                "total": total_rows,
                "processed": processed_rows,
                "errors": error_count,
                "status": "completed",
                "timestamp": timezone.now().isoformat(),
            },
        )
        logger.info("Completed import_csv_task task_id=%s", upload_task_id)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to process upload %s", upload_task_id)
        stacktrace = traceback.format_exc()
        error_count += 1
        error_details.insert(
            0,
            {
                "error": str(exc),
                "stacktrace": stacktrace,
            },
        )
        job.status = UploadJob.Status.FAILED
        job.errors_json = error_details[:MAX_ERROR_RECORDS]
        job.save(update_fields=["status", "errors_json", "updated_at"])

        failure_payload = _write_upload_progress(
            upload_task_id,
            status="failed",
            processed=processed_rows,
            total=total_rows,
            percent=_calculate_percent(processed_rows, total_rows),
            errors=error_count,
            error=str(exc),
        )
        self.update_state(state="FAILURE", meta=failure_payload)
        queue_event(
            Webhook.EVENT_IMPORT_COMPLETED,
            {
                "event": Webhook.EVENT_IMPORT_COMPLETED,
                "task_id": upload_task_id,
                "total": total_rows,
                "processed": processed_rows,
                "errors": error_count,
                "status": "failed",
                "error": str(exc),
                "timestamp": timezone.now().isoformat(),
            },
        )
        raise


@shared_task(bind=True, name="products.bulk_delete_products_task")
def bulk_delete_products_task(self, job_id: int, user_id: Optional[int] = None) -> None:
    """Delete all products in batches (or truncate) and report progress."""
    logger.info("Starting bulk_delete_products_task job_id=%s user_id=%s", job_id, user_id)

    job = DeletionJob.objects.filter(pk=job_id).first()
    if not job:
        logger.warning("DeletionJob with id=%s not found.", job_id)
        publish_delete_progress(
            job_id,
            status="failed",
            processed=0,
            total=0,
            percent=0,
            errors=1,
            error="Deletion job not found.",
        )
        return

    total = Product.objects.count()
    job.status = DeletionJob.Status.IN_PROGRESS
    job.total_count = total
    job.deleted_count = 0
    job.errors_json = []
    job.save(update_fields=["status", "total_count", "deleted_count", "errors_json", "updated_at"])

    if total == 0:
        payload = publish_delete_progress(
            job_id,
            status="completed",
            processed=0,
            total=0,
            percent=100,
            errors=0,
        )
        job.status = DeletionJob.Status.COMPLETED
        job.save(update_fields=["status", "updated_at"])
        self.update_state(state="SUCCESS", meta=payload)
        return

    batch_size = getattr(settings, "PRODUCT_DELETE_BATCH_SIZE", 1000)
    truncate_threshold = getattr(settings, "PRODUCT_DELETE_TRUNCATE_THRESHOLD", 200000)
    deleted_count = 0
    errors = 0

    payload = publish_delete_progress(
        job_id,
        status="in_progress",
        processed=deleted_count,
        total=total,
        percent=_calculate_percent(deleted_count, total),
        errors=errors,
    )
    self.update_state(state="PROGRESS", meta=payload)

    try:
        if total >= truncate_threshold:
            logger.info("Truncating products_product table (total=%s exceeds threshold=%s).", total, truncate_threshold)
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE products_product RESTART IDENTITY CASCADE;")
            deleted_count = total
        else:
            logger.info(
                "Deleting products in batches of %s (total=%s, threshold=%s).",
                batch_size,
                total,
                truncate_threshold,
            )
            while True:
                ids = list(Product.objects.values_list("pk", flat=True)[:batch_size])
                if not ids:
                    break
                deleted_batch, _ = Product.objects.filter(pk__in=ids).delete()
                deleted_count += deleted_batch
                job.deleted_count = deleted_count
                job.save(update_fields=["deleted_count", "updated_at"])

            payload = publish_delete_progress(
                job_id,
                status="in_progress",
                processed=deleted_count,
                total=total,
                percent=_calculate_percent(deleted_count, total),
                errors=errors,
            )
            self.update_state(state="PROGRESS", meta=payload)

        job.status = DeletionJob.Status.COMPLETED
        job.deleted_count = deleted_count
        job.save(update_fields=["status", "deleted_count", "updated_at"])

        payload = publish_delete_progress(
            job_id,
            status="completed",
            processed=deleted_count,
            total=total,
            percent=100,
            errors=errors,
        )
        self.update_state(state="SUCCESS", meta=payload)
        logger.info("Completed bulk_delete_products_task job_id=%s", job_id)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to bulk delete products job_id=%s", job_id)
        errors += 1
        job.status = DeletionJob.Status.FAILED
        job.errors_json = [{"message": str(exc), "stacktrace": traceback.format_exc()}]
        job.save(update_fields=["status", "errors_json", "updated_at"])

        payload = publish_delete_progress(
            job_id,
            status="failed",
            processed=deleted_count,
            total=total,
            percent=_calculate_percent(deleted_count, total),
            errors=errors,
            error=str(exc),
        )
        self.update_state(state="FAILURE", meta=payload)
        raise
