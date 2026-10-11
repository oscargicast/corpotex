from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("suppliers", views.SupplierViewSet, basename="supplier")

urlpatterns = router.urls + [
    path("suppliers/<int:pk>/numbers/<int:number_id>/", views.SupplierNumberView.as_view(), name="supplier-number"),
]
