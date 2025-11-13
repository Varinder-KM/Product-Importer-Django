import csv
import json
import logging
import traceback
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional, Tuple

import redis
from celery import shared_task
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from psycopg2 import sql

from .models import UploadJob
from .utils.csv_batch_loader import CSVBatchLoader

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None

ProgressPayload = Dict[str, Optional[object]]

TRUTHY_VALUES = {"1", "true", "yes", "y", "t"}
MAX_ERROR_RECORDS = 50


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def _calculate_percent(processed: int, total: int) -> int:
    if total <= 0:
        return 100 if processed > 0 else 0
    return min(100, int((processed / total) * 100))


def _write_progress(
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
    try:
        _get_redis_client().set(f"upload:{task_id}", json.dumps(payload))
    except redis.RedisError:
        logger.exception("Failed to write progress to Redis for task %s", task_id)
    return payload


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

    with transaction.atomic():
        with connection.cursor() as cursor:
            create_temp_sql = sql.SQL(
                """
                CREATE TEMP TABLE {temp_table} (
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
            ).format(temp_table=sql.Identifier(temp_table_name))
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
                    copy_sql = sql.SQL(
                        """
                        COPY {temp_table} (sku, sku_lower, name, description, price, active, created_at, updated_at)
                        FROM STDIN WITH CSV HEADER;
                        """
                    ).format(temp_table=sql.Identifier(temp_table_name))
                    cursor.copy_expert(copy_sql.as_string(cursor), read_handle)

                upsert_sql = sql.SQL(
                    """
                    INSERT INTO products_product (sku, name, description, price, active, created_at, updated_at)
                    SELECT
                        sku,
                        name,
                        description,
                        price,
                        active,
                        created_at,
                        updated_at
                    FROM {temp_table}
                    ON CONFLICT ON CONSTRAINT product_lower_sku_unique
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        price = EXCLUDED.price,
                        active = EXCLUDED.active,
                        updated_at = EXCLUDED.updated_at;
                    """
                ).format(temp_table=sql.Identifier(temp_table_name))
                cursor.execute(upsert_sql)
            finally:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {temp_table}").format(
                        temp_table=sql.Identifier(temp_table_name)
                    )
                )
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
        _write_progress(
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
        _write_progress(
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

    initial_payload = _write_progress(
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

            temp_table_name = f"tmp_products_upload_{upload_task_id[:8]}_{batch_index}"
            _copy_batch_to_database(normalized_rows, temp_table_name)

            job.processed_rows = processed_rows
            job.errors_json = error_details[:MAX_ERROR_RECORDS]
            job.save(update_fields=["processed_rows", "errors_json", "updated_at"])

            percent = _calculate_percent(processed_rows, total_rows)
            payload = _write_progress(
                upload_task_id,
                status="in_progress",
                processed=processed_rows,
                total=total_rows,
                percent=percent,
                errors=error_count,
            )
            self.update_state(state="PROGRESS", meta=payload)

        job.status = UploadJob.Status.COMPLETED
        job.processed_rows = processed_rows
        job.errors_json = error_details
        job.save(update_fields=["status", "processed_rows", "errors_json", "updated_at"])

        final_payload = _write_progress(
            upload_task_id,
            status="completed",
            processed=processed_rows,
            total=total_rows,
            percent=100,
            errors=error_count,
        )
        self.update_state(state="SUCCESS", meta=final_payload)
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

        failure_payload = _write_progress(
            upload_task_id,
            status="failed",
            processed=processed_rows,
            total=total_rows,
            percent=_calculate_percent(processed_rows, total_rows),
            errors=error_count,
            error=str(exc),
        )
        self.update_state(state="FAILURE", meta=failure_payload)
        raise
