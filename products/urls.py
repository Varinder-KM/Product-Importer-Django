from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet
from .views_upload import UploadCSVView, UploadPageView, UploadProgressView

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = router.urls + [
    path("uploads/ui/", UploadPageView.as_view(), name="product-upload-page"),
    path("uploads/", UploadCSVView.as_view(), name="product-upload"),
    path("uploads/<str:task_id>/progress/", UploadProgressView.as_view(), name="product-upload-progress"),
]
