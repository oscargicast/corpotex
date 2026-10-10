from rest_framework import viewsets

from core.permissions import IsManager
from core.serializers import serializer_for

from .models import Supplier


class SupplierViewSet(viewsets.ReadOnlyModelViewSet):
    """Suppliers and workshops. Manager only: the list carries phone numbers and prices."""

    permission_classes = [IsManager]
    queryset = Supplier.objects.prefetch_related("numbers", "rates__material", "rates__product")

    def get_serializer_class(self):
        return serializer_for(Supplier, "manager", detail=self.action == "retrieve")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for name in ("kind", "status", "source"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        return qs
