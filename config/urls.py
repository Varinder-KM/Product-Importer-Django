from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from products.views_upload import ProductManagementView, UploadPageView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/products/", permanent=False), name="home"),
    path("api/", include("products.urls")),
    path("api/", include("webhooks.urls")),
    path("upload/", UploadPageView.as_view(), name="upload-page"),
    path("products/", ProductManagementView.as_view(), name="products-ui"),
]

