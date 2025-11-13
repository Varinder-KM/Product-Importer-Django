from django.urls import path

from .consumers import DeletionProgressConsumer, UploadProgressConsumer

websocket_urlpatterns = [
    path("ws/uploads/<str:task_id>/", UploadProgressConsumer.as_asgi(), name="upload-progress"),
    path("ws/deletions/<str:job_id>/", DeletionProgressConsumer.as_asgi(), name="deletion-progress"),
]

