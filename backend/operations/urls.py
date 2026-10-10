from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("orders", views.OrderViewSet, basename="order")
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchase-order")
router.register("payments", views.PaymentViewSet, basename="payment")

urlpatterns = router.urls
