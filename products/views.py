from django_filters import rest_framework as filters
from rest_framework import pagination, viewsets

from .models import Product
from .serializers import ProductSerializer


class ProductFilterSet(filters.FilterSet):
    sku = filters.CharFilter(field_name="sku", lookup_expr="icontains")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    description = filters.CharFilter(field_name="description", lookup_expr="icontains")

    class Meta:
        model = Product
        fields = ["sku", "name", "active", "description"]


class ProductPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by("-created_at")
    serializer_class = ProductSerializer
    pagination_class = ProductPagination
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = ProductFilterSet

