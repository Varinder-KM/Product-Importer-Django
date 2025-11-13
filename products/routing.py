from django.urls import path

from .consumers import UploadProgressConsumer

websocket_urlpatterns = [
    path("ws/uploads/<str:task_id>/", UploadProgressConsumer.as_asgi(), name="upload-progress"),
]

