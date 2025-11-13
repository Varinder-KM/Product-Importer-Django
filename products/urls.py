from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet
from .views_upload import UploadCSVView

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = router.urls + [
    path("uploads/", UploadCSVView.as_view(), name="product-upload"),
]
