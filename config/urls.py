from django.contrib import admin
from django.urls import include, path

from products.views_upload import UploadPageView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("products.urls")),
    path("upload/", UploadPageView.as_view(), name="upload-page"),
]

