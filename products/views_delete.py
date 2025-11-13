from typing import Optional

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeletionJob, Product
from .tasks import bulk_delete_products_task, publish_delete_progress


class ProductBulkDeleteView(APIView):
    permission_classes = [permissions.AllowAny]

    def delete(self, request, *args, **kwargs):
        confirm = request.data.get("confirm")
        confirm_phrase = request.data.get("confirm_phrase")

        if confirm is not True:
            return Response({"detail": "Confirmation required."}, status=status.HTTP_400_BAD_REQUEST)

        expected_phrase = getattr(settings, "PRODUCT_DELETE_CONFIRM_PHRASE", "")
        if expected_phrase and (confirm_phrase or "").strip() != expected_phrase:
            return Response(
                {"detail": f"Invalid confirmation phrase. Expected '{expected_phrase}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total = Product.objects.count()
        threshold = getattr(settings, "PRODUCT_BULK_DELETE_THRESHOLD", 10000)

        if total == 0:
            return Response({"status": "completed", "deleted": 0})

        if total < threshold:
            deleted, _ = Product.objects.all().delete()
            return Response({"status": "completed", "deleted": deleted})

        user = request.user if request.user.is_authenticated else None
        job = DeletionJob.objects.create(
            user=user,
            status=DeletionJob.Status.PENDING,
            total_count=total,
            deleted_count=0,
        )

        task = bulk_delete_products_task.delay(job.id, user_id=user.id if user else None)
        job.task_id = task.id
        job.save(update_fields=["task_id"])

        publish_delete_progress(
            job.id,
            status="pending",
            processed=0,
            total=total,
            percent=0,
            errors=0,
        )

        return Response(
            {
                "status": "queued",
                "job_id": job.id,
                "task_id": job.task_id,
                "total": total,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DeletionProgressView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, job_id: int, *args, **kwargs):
        job = DeletionJob.objects.filter(pk=job_id).first()
        if not job:
            return Response({"job_id": job_id, "progress": None}, status=status.HTTP_404_NOT_FOUND)

        total = job.total_count or 0
        processed = job.deleted_count or 0
        if total <= 0:
            percent = 100 if processed > 0 else 0
        else:
            percent = min(100, int((processed / total) * 100))

        errors = job.errors_json or []
        error_message: Optional[str] = None
        if errors:
            first_error = errors[0]
            if isinstance(first_error, dict):
                error_message = first_error.get("error") or first_error.get("message")

        payload = {
            "status": job.status,
            "processed": processed,
            "total": total,
            "percent": percent,
            "errors": len(errors),
            "error": error_message,
        }
        return Response({"job_id": job_id, "progress": payload})

