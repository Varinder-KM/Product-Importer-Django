from pathlib import Path
from typing import Optional

from django.conf import settings
from django.views.generic import TemplateView
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UploadJob
from .tasks import import_csv_task


def _calculate_percent(processed: int, total: int) -> int:
    if total <= 0:
        return 100 if processed > 0 else 0
    return min(100, int((processed / total) * 100))


class UploadPageView(TemplateView):
    template_name = "upload.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delete_confirm_phrase"] = getattr(
            settings, "PRODUCT_DELETE_CONFIRM_PHRASE", "DELETE ALL PRODUCTS"
        )
        return context


class ProductManagementView(TemplateView):
    template_name = "products.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delete_confirm_phrase"] = getattr(
            settings, "PRODUCT_DELETE_CONFIRM_PHRASE", "DELETE ALL PRODUCTS"
        )
        return context


class UploadCSVView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]

    max_upload_size = 200 * 1024 * 1024  # 200 MB

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"detail": "No file uploaded under 'file' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size <= 0:
            return Response(
                {"detail": "Uploaded file is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > self.max_upload_size:
            return Response(
                {"detail": "Uploaded file exceeds the maximum allowed size."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        original_name = uploaded_file.name
        extension = Path(original_name).suffix.lower()
        if extension != ".csv":
            return Response(
                {"detail": "Only .csv files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        media_root = Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR / "media"))
        uploads_dir = media_root / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        upload_job_id = UploadJob.generate_task_id()
        stored_filename = f"{upload_job_id}.csv"
        final_path = uploads_dir / stored_filename

        with final_path.open("wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        job = UploadJob.objects.create(
            task_id=upload_job_id,
            filename=original_name,
            status=UploadJob.Status.PENDING,
        )

        user_id = request.user.id if request.user and request.user.is_authenticated else None
        import_csv_task.delay(upload_job_id, str(final_path), user_id=user_id)

        return Response({"task_id": upload_job_id, "job_id": job.id}, status=status.HTTP_202_ACCEPTED)


class UploadProgressView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, task_id: str, *args, **kwargs):
        job = UploadJob.objects.filter(task_id=task_id).first()
        if not job:
            return Response({"task_id": task_id, "progress": None}, status=status.HTTP_404_NOT_FOUND)

        total = job.total_rows or 0
        processed = job.processed_rows or 0
        percent = _calculate_percent(processed, total)

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
        return Response({"task_id": task_id, "progress": payload})