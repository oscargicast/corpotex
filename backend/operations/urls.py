from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("orders", views.OrderViewSet, basename="order")
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchase-order")
router.register("payments", views.PaymentViewSet, basename="payment")

urlpatterns = router.urls + [
    path("report/<uuid:token>/", views.PublicReportView.as_view(), name="public-report"),
]
