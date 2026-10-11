"""Customers and products for the order form (ADR 0025 B): every role reads them."""

from drf_spectacular.utils import extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer, Product
from .serializers import RelativeFileField


class CustomerSerializer(serializers.ModelSerializer):
    ruc = serializers.CharField(source="tax_id", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Customer
        fields = ["id", "name", "ruc", "kind", "kind_display", "address", "lat", "lng"]


class ProductSerializer(serializers.ModelSerializer):
    brand = serializers.SerializerMethodField()
    image = RelativeFileField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "code", "name", "brand", "image"]

    @extend_schema_field(inline_serializer("ProductBrand", fields={"id": serializers.IntegerField(), "name": serializers.CharField()}, allow_null=True))
    def get_brand(self, obj):
        return {"id": obj.brand_id, "name": obj.brand.name} if obj.brand_id else None


class CustomerListView(APIView):
    @extend_schema(responses={200: CustomerSerializer(many=True)})
    def get(self, request):
        queryset = Customer.objects.order_by("name")
        if request.query_params.get("q"):
            queryset = queryset.filter(name__icontains=request.query_params["q"].strip())
        return Response(CustomerSerializer(queryset, many=True, context={"request": request}).data)


class ProductListView(APIView):
    @extend_schema(responses={200: ProductSerializer(many=True)})
    def get(self, request):
        queryset = Product.objects.select_related("brand").order_by("code")
        params = request.query_params
        if params.get("brand"):
            queryset = queryset.filter(brand__name__iexact=params["brand"])
        if params.get("q"):
            text = params["q"].strip()
            queryset = queryset.filter(code__icontains=text) | queryset.filter(name__icontains=text)
        return Response(ProductSerializer(queryset.distinct(), many=True, context={"request": request}).data)
